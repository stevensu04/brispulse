"""Helpers for history tests: running trips and live states built in one line."""

import datetime as dt
from typing import Any

from brispulse.realtime.model import FeedName, FeedSnapshot, LiveState, TripState, Vehicle
from brispulse.realtime.normalise import (
    normalise_alerts,
    normalise_trip_updates,
    normalise_vehicles,
)
from brispulse.realtime.populations import RunningTrip
from brispulse.realtime.thresholds import DEFAULT_THRESHOLDS
from tests.rt_fixture import NOW, REFERENCE, feed

MONDAY = dt.date(2026, 11, 16)


def running(
    trip_id: str = "T1",
    delay: int | None = 60,
    *,
    implausible: bool = False,
    route_id: str = "R1",
    mode: str = "bus",
    service_date: dt.date = MONDAY,
    vehicle_id: str = "V1",
    relationship: str = "scheduled",
) -> RunningTrip:
    trip = TripState(
        trip_id=trip_id,
        route_id=route_id,
        mode=mode,
        start_date=service_date,
        start_time_s=8 * 3600,
        relationship=relationship,
        vehicle_id=vehicle_id,
        timestamp=None,
        next_stop_delay_s=delay,
        delay_implausible=implausible,
        predictions=(),
        matched=True,
    )
    vehicle = Vehicle(
        vehicle_id, None, trip_id, route_id, mode, -27.5, 153.0, None, None, None, 0, 0, True, True
    )
    return RunningTrip(trip=trip, vehicle=vehicle)


def live_state(
    *,
    vehicles: tuple[Any, ...] | None = None,
    trips: tuple[Any, ...] | None = None,
    alerts: tuple[Any, ...] | None = None,
    vehicles_at: int = NOW,
    trips_at: int = NOW,
    alerts_at: int = NOW,
) -> LiveState:
    """A live state from Protobuf entities. A feed left as None was never fetched."""
    state: dict[str, Any] = {}
    if vehicles is not None:
        items, stats = normalise_vehicles(
            feed(*vehicles, timestamp=vehicles_at), REFERENCE, DEFAULT_THRESHOLDS
        )
        state["vehicles"] = FeedSnapshot(
            FeedName.VEHICLE_POSITIONS, vehicles_at, vehicles_at, items, stats, 7
        )
    if trips is not None:
        trip_items, trip_stats = normalise_trip_updates(
            feed(*trips, timestamp=trips_at), REFERENCE, DEFAULT_THRESHOLDS
        )
        state["trip_updates"] = FeedSnapshot(
            FeedName.TRIP_UPDATES, trips_at, trips_at, trip_items, trip_stats, 7
        )
    if alerts is not None:
        alert_items, alert_stats = normalise_alerts(feed(*alerts, timestamp=alerts_at), REFERENCE)
        state["alerts"] = FeedSnapshot(
            FeedName.ALERTS, alerts_at, alerts_at, alert_items, alert_stats, 7
        )
    return LiveState(**state)
