"""Which trips count as "running" (architecture §6.1).

This definition decides what every delay figure means, so it lives in one place.

Measured on 2026-11-16: about half the trips in the TripUpdates feed are not running.
Trips that have not started and have no vehicle report a delay of zero ~95 % of the
time; trips that have not started but already have a vehicle (waiting at the terminus)
report delays of around -27 minutes. Including either group makes delay statistics
meaningless.
"""

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from brispulse.realtime.model import FeedSnapshot, TripState, Vehicle


@dataclass(frozen=True, slots=True)
class RunningTrip:
    trip: TripState
    vehicle: Vehicle


def service_start_epoch(start_date: dt.date, start_time_s: int, timezone: ZoneInfo) -> float:
    """When a trip is scheduled to start, as epoch seconds.

    GTFS counts time from midnight of the service day, and past 24:00:00 for trips
    that start after midnight but belong to the previous day's service.
    """
    midnight = dt.datetime.combine(start_date, dt.time(), tzinfo=timezone)
    return midnight.timestamp() + start_time_s


def running_trips(
    vehicles: FeedSnapshot[Vehicle],
    trip_updates: FeedSnapshot[TripState],
    timezone: ZoneInfo,
) -> list[RunningTrip]:
    """Trips that are actually in service, each with its vehicle.

    A trip is running when all of these hold:

    * it resolves in the static schedule and is not cancelled;
    * its scheduled start has passed, judged at the time the trip data was produced;
    * a vehicle is reporting for it, and that report is fresh.
    """
    fresh_vehicle_by_trip = {
        vehicle.trip_id: vehicle
        for vehicle in vehicles.items
        if vehicle.fresh and vehicle.trip_id is not None
    }
    as_of = trip_updates.source_timestamp
    running: list[RunningTrip] = []
    for trip in trip_updates.items:
        if not trip.matched or trip.canceled:
            continue
        if trip.start_date is None or trip.start_time_s is None:
            # Without a start we cannot tell a running trip from one waiting to begin.
            continue
        if service_start_epoch(trip.start_date, trip.start_time_s, timezone) > as_of:
            continue
        vehicle = fresh_vehicle_by_trip.get(trip.trip_id)
        if vehicle is None:
            continue
        running.append(RunningTrip(trip=trip, vehicle=vehicle))
    return running
