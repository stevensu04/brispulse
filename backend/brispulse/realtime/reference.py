"""In-memory lookups from the active static version.

The collector uses them to validate real-time IDs; the API uses them to put names on
routes, stops and trips. Everything a live endpoint needs is here, so those endpoints
keep working when the database is unreachable (architecture §7).
"""

import datetime as dt
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from brispulse.gtfs_static.loader import get_active_version
from brispulse.models import Route, Stop, Trip


class RouteInfo(NamedTuple):
    short_name: str | None
    long_name: str | None
    mode: str
    color: str | None
    text_color: str | None


class StopInfo(NamedTuple):
    name: str
    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class Reference:
    version_id: int
    routes: Mapping[str, RouteInfo]
    # Every scheduled trip, with its destination text where the schedule gives one.
    trip_headsigns: Mapping[str, str | None]
    stops: Mapping[str, StopInfo]
    # When TransLink published the schedule file, and the dates it covers.
    published_at: dt.datetime | None = None
    feed_start_date: dt.date | None = None
    feed_end_date: dt.date | None = None

    def mode_of(self, route_id: str | None) -> str | None:
        route = self.routes.get(route_id) if route_id else None
        return route.mode if route is not None else None

    def has_trip(self, trip_id: str | None) -> bool:
        return trip_id is not None and trip_id in self.trip_headsigns


def load_reference(session: Session) -> Reference | None:
    """Load the active version's lookups, or None when nothing has been imported yet."""
    version = get_active_version(session)
    if version is None:
        return None
    routes = session.execute(
        select(
            Route.route_id,
            Route.short_name,
            Route.long_name,
            Route.mode,
            Route.color,
            Route.text_color,
        ).where(Route.static_version_id == version.id)
    )
    trips = session.execute(
        select(Trip.trip_id, Trip.headsign).where(Trip.static_version_id == version.id)
    )
    stops = session.execute(
        select(Stop.stop_id, Stop.name, Stop.lat, Stop.lon).where(
            Stop.static_version_id == version.id
        )
    )
    return Reference(
        version_id=version.id,
        routes={
            row.route_id: RouteInfo(
                row.short_name, row.long_name, row.mode, row.color, row.text_color
            )
            for row in routes
        },
        # Interned: 173,183 trips share a few thousand distinct destinations.
        trip_headsigns={
            row.trip_id: sys.intern(row.headsign) if row.headsign else None for row in trips
        },
        stops={row.stop_id: StopInfo(row.name, row.lat, row.lon) for row in stops},
        published_at=version.last_modified,
        feed_start_date=version.feed_start_date,
        feed_end_date=version.feed_end_date,
    )


def active_version_id(session: Session) -> int | None:
    version = get_active_version(session)
    return version.id if version is not None else None
