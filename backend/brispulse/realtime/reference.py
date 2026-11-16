"""In-memory lookups from the active static version, used to validate real-time IDs."""

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from brispulse.gtfs_static.loader import get_active_version
from brispulse.models import Route, Stop, Trip


@dataclass(frozen=True, slots=True)
class Reference:
    version_id: int
    route_modes: Mapping[str, str]
    trip_ids: frozenset[str]
    stop_ids: frozenset[str]


def load_reference(session: Session) -> Reference | None:
    """Load the active version's IDs, or None when nothing has been imported yet."""
    version = get_active_version(session)
    if version is None:
        return None
    routes = session.execute(
        select(Route.route_id, Route.mode).where(Route.static_version_id == version.id)
    )
    trips = session.scalars(select(Trip.trip_id).where(Trip.static_version_id == version.id))
    stops = session.scalars(select(Stop.stop_id).where(Stop.static_version_id == version.id))
    return Reference(
        version_id=version.id,
        route_modes={row.route_id: row.mode for row in routes},
        trip_ids=frozenset(trips),
        stop_ids=frozenset(stops),
    )


def active_version_id(session: Session) -> int | None:
    version = get_active_version(session)
    return version.id if version is not None else None
