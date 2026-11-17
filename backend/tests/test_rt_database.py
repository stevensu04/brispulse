"""Real-time code that touches PostgreSQL: the fetch log and the static reference."""

import datetime as dt
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from brispulse.config import Settings
from brispulse.gtfs_static import service
from brispulse.models import FeedFetch
from brispulse.realtime.collector import FetchRecord, Outcome
from brispulse.realtime.fetch_log import make_fetch_recorder
from brispulse.realtime.model import FeedName
from brispulse.realtime.reference import load_reference
from brispulse.runtime import ReferenceHolder
from tests.gtfs_fixture import DEFAULT_FILES, write_zip

pytestmark = pytest.mark.db

WHEN = dt.datetime(2026, 11, 16, 9, 0, tzinfo=dt.UTC)


def test_a_successful_fetch_is_logged(session_factory: sessionmaker[Session]) -> None:
    record = FetchRecord(
        feed=FeedName.VEHICLE_POSITIONS,
        fetched_at=WHEN,
        duration_ms=412,
        outcome=Outcome.OK,
        http_status=200,
        body_bytes=253_212,
        source_timestamp=WHEN - dt.timedelta(seconds=20),
        entity_count=1615,
        accepted_count=1589,
        rejected={"bad_position": 2},
        anomaly=False,
        static_version_id=3,
    )

    make_fetch_recorder(session_factory)(record)

    with session_factory() as session:
        row = session.scalars(select(FeedFetch)).one()
        assert (row.feed, row.outcome, row.http_status) == ("vehicle_positions", "ok", 200)
        assert (row.entity_count, row.accepted_count, row.duration_ms) == (1615, 1589, 412)
        assert row.rejected == {"bad_position": 2}
        assert row.fetched_at == WHEN
        assert row.source_timestamp == WHEN - dt.timedelta(seconds=20)
        assert (row.anomaly, row.static_version_id) == (False, 3)


def test_a_failed_fetch_is_logged_with_its_missing_values_missing(
    session_factory: sessionmaker[Session],
) -> None:
    record = FetchRecord(
        feed=FeedName.ALERTS,
        fetched_at=WHEN,
        duration_ms=10_003,
        outcome=Outcome.NETWORK_ERROR,
        detail="ConnectTimeout: timed out",
    )

    make_fetch_recorder(session_factory)(record)

    with session_factory() as session:
        row = session.scalars(select(FeedFetch)).one()
        assert (row.outcome, row.detail) == ("network_error", "ConnectTimeout: timed out")
        assert (row.http_status, row.entity_count, row.accepted_count) == (None, None, None)
        assert (row.source_timestamp, row.rejected) == (None, None)
        # A real SQL NULL, so `WHERE rejected IS NULL` and JSON comparisons behave.
        assert session.scalar(select(func.count()).where(FeedFetch.rejected.is_(None))) == 1


def test_reference_is_none_until_a_schedule_is_imported(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        assert load_reference(session) is None

    holder = ReferenceHolder(session_factory)
    assert holder.refresh() is False
    assert holder.current is None


def test_reference_holds_the_active_versions_ids(
    settings: Settings, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    result = service.run_import(
        settings, session_factory, local_file=write_zip(tmp_path / "feed.zip")
    )

    with session_factory() as session:
        reference = load_reference(session)

    assert reference is not None
    assert reference.version_id == result.version_id
    assert {route_id: route.mode for route_id, route in reference.routes.items()} == {
        "R1": "bus",
        "R2": "rail",
    }
    assert reference.routes["R1"] == ("100", "City Loop", "bus", "00FF00", "000000")
    assert reference.trip_headsigns == {"T1": "City", "T2": "City", "T3": "Northside"}
    assert set(reference.stops) == {"S1", "S2", "ST1"}
    assert reference.stops["ST1"].name == "Central Station"
    assert reference.feed_end_date == dt.date(2027, 1, 13)
    assert (reference.mode_of("R2"), reference.mode_of("R404"), reference.mode_of(None)) == (
        "rail",
        None,
        None,
    )
    assert (reference.has_trip("T1"), reference.has_trip("T404"), reference.has_trip(None)) == (
        True,
        False,
        False,
    )


def test_holder_reloads_only_when_the_active_version_changes(
    settings: Settings, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    holder = ReferenceHolder(session_factory)
    service.run_import(settings, session_factory, local_file=write_zip(tmp_path / "a.zip"))

    assert holder.refresh() is True
    first = holder.current
    assert holder.refresh() is False
    assert holder.current is first

    more_routes = {"routes.txt": DEFAULT_FILES["routes.txt"] + "R3,300,Extra,,4,,,\n"}
    service.run_import(
        settings, session_factory, local_file=write_zip(tmp_path / "b.zip", more_routes)
    )

    assert holder.refresh() is True
    assert holder.current is not None and holder.current is not first
    assert holder.current.mode_of("R3") == "ferry"
