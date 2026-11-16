"""The importer against a real PostgreSQL database."""

from pathlib import Path

import httpx2
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from brispulse.config import Settings
from brispulse.gtfs_static import loader, service
from brispulse.gtfs_static.fetch import FetchError
from brispulse.gtfs_static.parse import GtfsFormatError
from brispulse.models import (
    Route,
    ServiceCalendar,
    ServiceCalendarDate,
    StaticVersion,
    Stop,
    Trip,
)
from tests.gtfs_fixture import DEFAULT_FILES, build_zip_bytes, write_zip

pytestmark = pytest.mark.db

HEADERS = {"ETag": '"v1"', "Last-Modified": "Fri, 13 Nov 2026 19:45:24 GMT"}


def count(session: Session, model: type, version_id: int | None = None) -> int:
    query = select(func.count()).select_from(model)
    if version_id is not None:
        query = query.where(model.static_version_id == version_id)  # type: ignore[attr-defined]
    return session.scalar(query) or 0


def bigger_feed(extra_routes: int) -> dict[str, str | None]:
    """The default feed plus extra routes, so its content hash differs."""
    extra = "".join(f"X{i},{i},Extra {i},,3,,,\n" for i in range(extra_routes))
    return {"routes.txt": DEFAULT_FILES["routes.txt"] + extra}


class FakeTransLink:
    """Serves a zip over a mock transport and records the requests it receives."""

    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.body = body
        self.headers = HEADERS if headers is None else headers
        self.status = 200
        self.methods: list[str] = []

    def client(self) -> httpx2.Client:
        def handle(request: httpx2.Request) -> httpx2.Response:
            self.methods.append(request.method)
            if self.status != 200:
                return httpx2.Response(self.status)
            content = b"" if request.method == "HEAD" else self.body
            return httpx2.Response(200, content=content, headers=self.headers)

        return httpx2.Client(transport=httpx2.MockTransport(handle))


def test_import_loads_every_table(
    settings: Settings, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    result = service.run_import(
        settings, session_factory, local_file=write_zip(tmp_path / "feed.zip")
    )

    assert result.outcome is service.Outcome.IMPORTED
    with session_factory() as session:
        version = loader.get_active_version(session)
        assert version is not None
        assert version.id == result.version_id
        assert (version.route_count, version.stop_count, version.trip_count) == (2, 3, 3)
        assert version.stop_time_rows == 7
        assert version.feed_publisher == "Test Publisher"
        assert version.source_url == "file:feed.zip"
        assert version.report["files"]["trips.txt"]["accepted"] == 3
        assert count(session, Route, version.id) == 2
        assert count(session, Stop, version.id) == 3
        assert count(session, Trip, version.id) == 3
        assert count(session, ServiceCalendar, version.id) == 2
        assert count(session, ServiceCalendarDate, version.id) == 2

        late_trip = session.get(Trip, (version.id, "T2"))
        assert late_trip is not None
        assert late_trip.first_departure_s == 85_800
        assert late_trip.last_arrival_s == 88_200
        assert (late_trip.first_stop_id, late_trip.last_stop_id) == ("S2", "S1")


def test_identical_file_is_not_imported_twice(
    settings: Settings, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    path = write_zip(tmp_path / "feed.zip")
    first = service.run_import(settings, session_factory, local_file=path)

    second = service.run_import(settings, session_factory, local_file=path)

    assert second.outcome is service.Outcome.UNCHANGED
    assert second.version_id == first.version_id
    with session_factory() as session:
        assert count(session, StaticVersion) == 1


def test_force_reimports_an_identical_file(
    settings: Settings, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    path = write_zip(tmp_path / "feed.zip")
    service.run_import(settings, session_factory, local_file=path)

    forced = service.run_import(settings, session_factory, local_file=path, force=True)

    assert forced.outcome is service.Outcome.IMPORTED
    with session_factory() as session:
        assert count(session, StaticVersion) == 2


def test_new_version_replaces_the_active_one_and_keeps_the_old(
    settings: Settings, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    first = service.run_import(settings, session_factory, local_file=write_zip(tmp_path / "a.zip"))

    second = service.run_import(
        settings, session_factory, local_file=write_zip(tmp_path / "b.zip", bigger_feed(1))
    )

    with session_factory() as session:
        active = loader.get_active_version(session)
        assert active is not None and active.id == second.version_id
        assert count(session, StaticVersion) == 2
        # The previous version's rows are still there, for rollback.
        assert first.version_id is not None
        assert count(session, Route, first.version_id) == 2
        assert count(session, Route, active.id) == 3


def test_only_the_newest_versions_are_kept(
    settings: Settings, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    for extra in range(5):
        service.run_import(
            settings,
            session_factory,
            local_file=write_zip(tmp_path / f"{extra}.zip", bigger_feed(extra)),
        )

    with session_factory() as session:
        ids = session.scalars(select(StaticVersion.id).order_by(StaticVersion.id)).all()
        assert list(ids) == [3, 4, 5]
        assert loader.get_active_version(session).id == 5  # type: ignore[union-attr]
        # Pruned versions take their rows with them.
        assert count(session, Trip) == 9


def test_database_refuses_two_active_versions(
    settings: Settings, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    path = write_zip(tmp_path / "feed.zip")
    service.run_import(settings, session_factory, local_file=path)
    service.run_import(settings, session_factory, local_file=path, force=True)

    with pytest.raises(IntegrityError), session_factory.begin() as session:
        for version in session.scalars(select(StaticVersion)):
            version.is_active = True


def test_a_feed_that_shrank_by_more_than_half_is_refused(
    settings: Settings, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    service.run_import(
        settings, session_factory, local_file=write_zip(tmp_path / "big.zip", bigger_feed(10))
    )

    with pytest.raises(loader.SuspiciousFeedError, match="routes dropped from 12 to 2"):
        service.run_import(settings, session_factory, local_file=write_zip(tmp_path / "small.zip"))

    with session_factory() as session:
        active = loader.get_active_version(session)
        assert active is not None and active.route_count == 12
        assert count(session, StaticVersion) == 1


def test_force_overrides_the_shrink_guard(
    settings: Settings, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    service.run_import(
        settings, session_factory, local_file=write_zip(tmp_path / "big.zip", bigger_feed(10))
    )

    result = service.run_import(
        settings, session_factory, local_file=write_zip(tmp_path / "small.zip"), force=True
    )

    assert result.outcome is service.Outcome.IMPORTED


def test_a_feed_with_no_trips_is_refused(
    settings: Settings, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    header = DEFAULT_FILES["trips.txt"].splitlines()[0] + "\n"

    with pytest.raises(loader.EmptyFeedError, match="no trips"):
        service.run_import(
            settings,
            session_factory,
            local_file=write_zip(tmp_path / "empty.zip", {"trips.txt": header}),
        )

    with session_factory() as session:
        assert count(session, StaticVersion) == 0


def test_a_failed_import_leaves_the_active_version_untouched(
    settings: Settings, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    good = service.run_import(
        settings, session_factory, local_file=write_zip(tmp_path / "good.zip")
    )
    broken = write_zip(tmp_path / "broken.zip", {"stops.txt": None})

    with pytest.raises(GtfsFormatError, match=r"stops\.txt is missing"):
        service.run_import(settings, session_factory, local_file=broken)

    with session_factory() as session:
        active = loader.get_active_version(session)
        assert active is not None and active.id == good.version_id
        assert count(session, Stop) == 3


def test_a_file_that_is_not_a_zip_is_refused(
    settings: Settings, session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    path = tmp_path / "feed.zip"
    path.write_bytes(b"<html>Service unavailable</html>")

    with pytest.raises(GtfsFormatError, match="not a zip"):
        service.run_import(settings, session_factory, local_file=path)


def test_download_and_import_records_the_server_markers(
    settings: Settings, session_factory: sessionmaker[Session]
) -> None:
    translink = FakeTransLink(build_zip_bytes())

    result = service.run_import(settings, session_factory, client=translink.client())

    assert result.outcome is service.Outcome.IMPORTED
    # Nothing is active yet, so there is no point asking the server first.
    assert translink.methods == ["GET"]
    with session_factory() as session:
        version = loader.get_active_version(session)
        assert version is not None
        assert version.etag == '"v1"'
        assert version.last_modified is not None
        assert version.source_url == "https://translink.test/GTFS/SEQ_GTFS.zip"


def test_unchanged_server_file_is_not_downloaded_again(
    settings: Settings, session_factory: sessionmaker[Session]
) -> None:
    translink = FakeTransLink(build_zip_bytes())
    service.run_import(settings, session_factory, client=translink.client())
    translink.methods.clear()

    result = service.run_import(settings, session_factory, client=translink.client())

    assert result.outcome is service.Outcome.UNCHANGED
    assert translink.methods == ["HEAD"]


def test_changed_server_markers_trigger_a_download(
    settings: Settings, session_factory: sessionmaker[Session]
) -> None:
    translink = FakeTransLink(build_zip_bytes())
    service.run_import(settings, session_factory, client=translink.client())
    translink.body = build_zip_bytes(bigger_feed(1))
    translink.headers = {"ETag": '"v2"', "Last-Modified": "Sat, 14 Nov 2026 19:45:24 GMT"}
    translink.methods.clear()

    result = service.run_import(settings, session_factory, client=translink.client())

    assert result.outcome is service.Outcome.IMPORTED
    assert translink.methods == ["HEAD", "GET"]
    assert service.remote_has_changed(translink.client(), settings, session_factory) is False


def test_new_markers_on_identical_content_do_not_create_a_version(
    settings: Settings, session_factory: sessionmaker[Session]
) -> None:
    translink = FakeTransLink(build_zip_bytes())
    service.run_import(settings, session_factory, client=translink.client())
    translink.headers = {"ETag": '"v2"', "Last-Modified": "Sat, 14 Nov 2026 19:45:24 GMT"}

    result = service.run_import(settings, session_factory, client=translink.client())

    assert result.outcome is service.Outcome.UNCHANGED
    assert "sha256" in result.detail
    with session_factory() as session:
        assert count(session, StaticVersion) == 1


def test_missing_server_markers_fall_back_to_comparing_content(
    settings: Settings, session_factory: sessionmaker[Session]
) -> None:
    translink = FakeTransLink(build_zip_bytes(), headers={})
    service.run_import(settings, session_factory, client=translink.client())
    translink.methods.clear()

    result = service.run_import(settings, session_factory, client=translink.client())

    assert result.outcome is service.Outcome.UNCHANGED
    assert translink.methods == ["HEAD", "GET"]


def test_server_error_leaves_the_active_version_untouched(
    settings: Settings, session_factory: sessionmaker[Session]
) -> None:
    translink = FakeTransLink(build_zip_bytes())
    good = service.run_import(settings, session_factory, client=translink.client())
    translink.status = 503

    with pytest.raises(FetchError, match="HTTP 503"):
        service.run_import(settings, session_factory, client=translink.client())

    with session_factory() as session:
        active = loader.get_active_version(session)
        assert active is not None and active.id == good.version_id
