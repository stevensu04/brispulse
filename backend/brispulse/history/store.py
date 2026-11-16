"""Reads and writes of the history tables. All functions run inside the caller's transaction."""

import dataclasses
import datetime as dt
import hashlib
import json
from collections.abc import Iterable, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from brispulse.history.accumulator import TripSummary
from brispulse.history.sampling import NetworkSampleRow
from brispulse.history.schedule import scheduled_trips_per_route
from brispulse.models import AlertRecord, FeedFetch, NetworkSample, RouteDayStats, TripRecord
from brispulse.realtime.model import Alert
from brispulse.realtime.thresholds import Thresholds

_BATCH = 2_000


def _batches[T](rows: Sequence[T]) -> Iterable[Sequence[T]]:
    for start in range(0, len(rows), _BATCH):
        yield rows[start : start + _BATCH]


# --- trip records -----------------------------------------------------------------


def upsert_trip_records(session: Session, summaries: Sequence[TripSummary]) -> None:
    """Insert each summary, or replace the row its trip already has."""
    if not summaries:
        return
    statement = pg_insert(TripRecord)
    replaced = {
        column.name: statement.excluded[column.name]
        for column in TripRecord.__table__.columns
        if not column.primary_key
    }
    statement = statement.on_conflict_do_update(
        index_elements=[TripRecord.service_date, TripRecord.trip_id], set_=replaced
    )
    rows = [dataclasses.asdict(summary) for summary in summaries]
    for batch in _batches(rows):
        session.execute(statement, batch)


def load_in_flight(session: Session) -> list[TripSummary]:
    """Trips that were still being observed when they were last written."""
    fields = [field.name for field in dataclasses.fields(TripSummary)]
    records = session.scalars(select(TripRecord).where(TripRecord.completed.is_(False)))
    return [TripSummary(**{name: getattr(record, name) for name in fields}) for record in records]


# --- network samples --------------------------------------------------------------


def write_network_samples(session: Session, rows: Sequence[NetworkSampleRow]) -> None:
    if not rows:
        return
    statement = pg_insert(NetworkSample)
    replaced = {
        column.name: statement.excluded[column.name]
        for column in NetworkSample.__table__.columns
        if not column.primary_key
    }
    # Idempotent: writing the same five-minute slot twice keeps one row per mode.
    statement = statement.on_conflict_do_update(
        index_elements=[NetworkSample.sampled_at, NetworkSample.mode], set_=replaced
    )
    session.execute(statement, [dataclasses.asdict(row) for row in rows])


# --- alerts -----------------------------------------------------------------------


def alert_content_hash(alert: Alert) -> str:
    """Identifies an alert's content, so a reworded alert is stored as a new version."""
    content = [
        alert.cause,
        alert.effect,
        alert.header,
        alert.description,
        alert.url,
        [list(period) for period in alert.active_periods],
        list(alert.route_ids),
        list(alert.stop_ids),
    ]
    return hashlib.sha1(json.dumps(content, sort_keys=True).encode()).hexdigest()


def upsert_alerts(session: Session, alerts: Sequence[Alert], seen_at: dt.datetime) -> None:
    """Record every alert in the feed: new content is inserted, known content is re-dated."""
    if not alerts:
        return
    statement = pg_insert(AlertRecord)
    statement = statement.on_conflict_do_update(
        index_elements=[AlertRecord.alert_id, AlertRecord.content_hash],
        set_={"last_seen_at": statement.excluded.last_seen_at},
    )
    session.execute(
        statement,
        [
            {
                "alert_id": alert.alert_id,
                "content_hash": alert_content_hash(alert),
                "first_seen_at": seen_at,
                "last_seen_at": seen_at,
                "cause": alert.cause,
                "effect": alert.effect,
                "header": alert.header,
                "description": alert.description,
                "url": alert.url,
                "active_periods": [list(period) for period in alert.active_periods],
                "route_ids": list(alert.route_ids),
                "stop_ids": list(alert.stop_ids),
            }
            for alert in alerts
        ],
    )


# --- daily rollup -----------------------------------------------------------------


def service_dates_to_roll_up(
    session: Session, now: float, timezone: ZoneInfo, thresholds: Thresholds
) -> list[dt.date]:
    """Closed service days that have trip records but no rollup yet.

    A service day is closed once ``service_day_closes_after_s`` has passed since its
    midnight, because its last trips run well into the next calendar day.
    """
    rolled_up = select(RouteDayStats.service_date).distinct()
    candidates = session.scalars(
        select(TripRecord.service_date)
        .where(TripRecord.service_date.not_in(rolled_up))
        .distinct()
        .order_by(TripRecord.service_date)
    )
    closed: list[dt.date] = []
    for service_date in candidates:
        midnight = dt.datetime.combine(service_date, dt.time(), tzinfo=timezone).timestamp()
        if midnight + thresholds.service_day_closes_after_s <= now:
            closed.append(service_date)
    return closed


def roll_up_service_date(
    session: Session,
    service_date: dt.date,
    *,
    thresholds: Thresholds,
    static_version_id: int | None,
    computed_at: dt.datetime,
) -> int:
    """Rebuild ``route_day_stats`` for one service day. Safe to run again.

    Each trip contributes its own median delay, and only if it was observed at least
    ``min_observations_per_trip`` times. Percentiles use ``percentile_disc``, the same
    nearest-rank rule as the live figures, and are withheld below ``min_sample`` trips.
    """
    session.execute(delete(RouteDayStats).where(RouteDayStats.service_date == service_date))
    median = TripRecord.delay_median_s
    per_route = session.execute(
        select(
            TripRecord.route_id,
            func.max(TripRecord.mode),
            func.count(),
            func.percentile_disc(0.5).within_group(median.asc()),
            func.percentile_disc(0.9).within_group(median.asc()),
            func.count().filter(median < -thresholds.delay_early_s),
            func.count().filter(median > thresholds.delay_late_s),
        )
        .where(
            TripRecord.service_date == service_date,
            TripRecord.route_id.is_not(None),
            median.is_not(None),
            TripRecord.obs_count >= thresholds.min_observations_per_trip,
        )
        .group_by(TripRecord.route_id)
    ).all()

    scheduled = (
        scheduled_trips_per_route(session, static_version_id, service_date)
        if static_version_id is not None
        else {}
    )
    rows = []
    for route_id, mode, trips, p50, p90, early, late in per_route:
        enough = trips >= thresholds.min_sample
        rows.append(
            {
                "service_date": service_date,
                "route_id": route_id,
                "mode": mode,
                "trips_observed": trips,
                # An empty lookup means the schedule in use does not cover that date.
                "trips_scheduled": scheduled.get(route_id) if scheduled else None,
                "delay_p50_s": p50 if enough else None,
                "delay_p90_s": p90 if enough else None,
                "trips_early": early,
                "trips_within_band": trips - early - late,
                "trips_late": late,
                "computed_at": computed_at,
            }
        )
    if rows:
        session.execute(pg_insert(RouteDayStats), rows)
    return len(rows)


# --- retention --------------------------------------------------------------------


def apply_retention(
    session: Session, *, today: dt.date, now: dt.datetime, fetch_days: int, trip_days: int
) -> dict[str, int]:
    """Delete rows past their retention period. Returns how many went, per table.

    Trip records are deleted only for service days that have been rolled up: if the
    rollup never ran, the rows it would need are kept (architecture §17, W8).
    """
    fetches = session.execute(
        delete(FeedFetch).where(FeedFetch.fetched_at < now - dt.timedelta(days=fetch_days))
    )
    rolled_up = select(RouteDayStats.service_date).distinct()
    trips = session.execute(
        delete(TripRecord).where(
            TripRecord.service_date < today - dt.timedelta(days=trip_days),
            TripRecord.service_date.in_(rolled_up),
        )
    )
    return {
        "feed_fetch": int(fetches.rowcount or 0),  # type: ignore[attr-defined]
        "trip_record": int(trips.rowcount or 0),  # type: ignore[attr-defined]
    }
