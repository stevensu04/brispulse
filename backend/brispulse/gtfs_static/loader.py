"""Write a parsed feed to the database as a new static version."""

import dataclasses
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from brispulse.gtfs_static.fetch import Download
from brispulse.gtfs_static.parse import ParsedFeed
from brispulse.models import (
    Base,
    Route,
    ServiceCalendar,
    ServiceCalendarDate,
    StaticVersion,
    Stop,
    Trip,
)

_BATCH_SIZE = 5_000

# A new feed with less than half the routes, stops or trips of the active one is far
# more likely to be a broken publication than a real network change. The threshold is a
# judgement call, not a measured value; ``force`` overrides it.
MAX_SHRINK_FRACTION = 0.5

# How many versions to keep, the active one included (architecture §5.1).
VERSIONS_TO_KEEP = 3


class EmptyFeedError(Exception):
    """The feed parsed, but holds no routes, stops or trips."""


class SuspiciousFeedError(Exception):
    """The feed is much smaller than the active version."""


def get_active_version(session: Session) -> StaticVersion | None:
    return session.scalars(select(StaticVersion).where(StaticVersion.is_active)).one_or_none()


def _check_plausible(feed: ParsedFeed, active: StaticVersion | None, force: bool) -> None:
    counts = {"routes": len(feed.routes), "stops": len(feed.stops), "trips": len(feed.trips)}
    empty = [name for name, count in counts.items() if count == 0]
    if empty:
        raise EmptyFeedError(f"feed has no {', '.join(empty)}")
    if active is None or force:
        return
    previous = {
        "routes": active.route_count,
        "stops": active.stop_count,
        "trips": active.trip_count,
    }
    for name, count in counts.items():
        if count < previous[name] * (1 - MAX_SHRINK_FRACTION):
            raise SuspiciousFeedError(
                f"{name} dropped from {previous[name]} to {count}; "
                "refusing to activate (use --force to override)"
            )


def _insert_rows(
    session: Session,
    table: type[Base],
    version_id: int,
    rows: Iterable[Any],
) -> None:
    batch: list[dict[str, Any]] = []
    for row in rows:
        batch.append({"static_version_id": version_id, **dataclasses.asdict(row)})
        if len(batch) >= _BATCH_SIZE:
            session.execute(insert(table), batch)
            batch = []
    if batch:
        session.execute(insert(table), batch)


def load_version(
    session: Session,
    feed: ParsedFeed,
    source: Download,
    source_url: str,
    *,
    force: bool = False,
) -> StaticVersion:
    """Store ``feed`` as a new version and make it the active one.

    Runs inside the caller's transaction: either the whole version becomes active, or
    nothing changes and the previous version stays in place.
    """
    active = get_active_version(session)
    _check_plausible(feed, active, force)

    version = StaticVersion(
        source_url=source_url,
        sha256=source.sha256,
        size_bytes=source.size_bytes,
        etag=source.remote.etag,
        last_modified=source.remote.last_modified,
        feed_publisher=feed.feed_info.publisher,
        feed_start_date=feed.feed_info.start_date,
        feed_end_date=feed.feed_info.end_date,
        route_count=len(feed.routes),
        stop_count=len(feed.stops),
        trip_count=len(feed.trips),
        stop_time_rows=feed.files["stop_times.txt"].rows_read,
        report=feed.report(),
        is_active=False,
    )
    session.add(version)
    session.flush()  # assigns version.id

    tables: Sequence[tuple[type[Base], Iterable[Any]]] = (
        (Route, feed.routes),
        (Stop, feed.stops),
        (Trip, feed.trips),
        (ServiceCalendar, feed.calendars),
        (ServiceCalendarDate, feed.calendar_dates),
    )
    for table, rows in tables:
        _insert_rows(session, table, version.id, rows)

    # Deactivate first: the database allows only one active version at any moment.
    session.execute(update(StaticVersion).where(StaticVersion.is_active).values(is_active=False))
    version.is_active = True
    session.flush()
    return version


def prune_versions(session: Session, keep: int = VERSIONS_TO_KEEP) -> list[int]:
    """Delete all but the newest ``keep`` versions. The active version is never deleted."""
    newest = session.scalars(
        select(StaticVersion.id).order_by(StaticVersion.id.desc()).limit(keep)
    ).all()
    doomed = session.scalars(
        select(StaticVersion.id).where(
            StaticVersion.id.not_in(newest),
            StaticVersion.is_active.is_(False),
        )
    ).all()
    if doomed:
        # Child rows go with their version (ON DELETE CASCADE).
        session.execute(delete(StaticVersion).where(StaticVersion.id.in_(doomed)))
    return list(doomed)
