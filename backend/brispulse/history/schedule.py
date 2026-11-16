"""Which trips does the static schedule say should be in progress? (architecture §6.1)

Used for real-time coverage: of the trips that should be running, how many have live
data. GTFS counts a trip's times from midnight of its service day, and a service day
runs past midnight (the latest trip ended at 30:33 when measured on 2026-11-16), so
"now" has to be checked against today's services and yesterday's.
"""

import datetime as dt
from collections.abc import Mapping
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from brispulse.models import Route, ServiceCalendar, ServiceCalendarDate, Trip

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def active_service_ids(session: Session, version_id: int, date: dt.date) -> set[str]:
    """Services that operate on ``date``: the weekly calendar, then that date's exceptions."""
    weekday = getattr(ServiceCalendar, _WEEKDAYS[date.weekday()])
    services = set(
        session.scalars(
            select(ServiceCalendar.service_id).where(
                ServiceCalendar.static_version_id == version_id,
                weekday.is_(True),
                ServiceCalendar.start_date <= date,
                ServiceCalendar.end_date >= date,
            )
        )
    )
    exceptions = session.execute(
        select(ServiceCalendarDate.service_id, ServiceCalendarDate.exception_type).where(
            ServiceCalendarDate.static_version_id == version_id,
            ServiceCalendarDate.date == date,
        )
    )
    for service_id, exception_type in exceptions:
        if exception_type == 1:
            services.add(service_id)
        else:
            services.discard(service_id)
    return services


def _in_progress(
    session: Session, version_id: int, service_date: dt.date, seconds: int
) -> dict[str, str]:
    services = active_service_ids(session, version_id, service_date)
    if not services:
        return {}
    rows = session.execute(
        select(Trip.trip_id, Route.mode)
        .join(
            Route,
            (Route.static_version_id == Trip.static_version_id) & (Route.route_id == Trip.route_id),
        )
        .where(
            Trip.static_version_id == version_id,
            Trip.service_id.in_(services),
            Trip.first_departure_s <= seconds,
            Trip.last_arrival_s >= seconds,
        )
    )
    return {row.trip_id: row.mode for row in rows}


def scheduled_in_progress(
    session: Session, version_id: int, now: float, timezone: ZoneInfo
) -> Mapping[str, str]:
    """Trip ID -> mode for every trip scheduled to be between its first and last stop."""
    local = dt.datetime.fromtimestamp(now, timezone)
    seconds = local.hour * 3600 + local.minute * 60 + local.second
    today = local.date()
    trips = _in_progress(session, version_id, today, seconds)
    # Yesterday's service day is still running if any of its trips go past midnight.
    trips.update(_in_progress(session, version_id, today - dt.timedelta(days=1), seconds + 86_400))
    return trips


def scheduled_trips_per_route(
    session: Session, version_id: int, service_date: dt.date
) -> Mapping[str, int]:
    """Route ID -> number of trips the schedule lists for ``service_date``."""
    services = active_service_ids(session, version_id, service_date)
    if not services:
        return {}
    counts: dict[str, int] = {}
    rows = session.scalars(
        select(Trip.route_id).where(
            Trip.static_version_id == version_id, Trip.service_id.in_(services)
        )
    )
    for route_id in rows:
        counts[route_id] = counts.get(route_id, 0) + 1
    return counts
