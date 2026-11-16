"""Which trips count as running. Each excluded case was observed in the live feeds."""

import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

from brispulse.realtime.model import FeedName, FeedSnapshot, TripState, Vehicle
from brispulse.realtime.normalise import normalise_trip_updates, normalise_vehicles
from brispulse.realtime.populations import running_trips, service_start_epoch
from brispulse.realtime.thresholds import DEFAULT_THRESHOLDS as T
from tests.rt_fixture import CANCELED, NOW, REFERENCE, feed, trip_update, vehicle

BRISBANE = ZoneInfo("Australia/Brisbane")


def snapshots(
    vehicles: list[Any], trips: list[Any]
) -> tuple[FeedSnapshot[Vehicle], FeedSnapshot[TripState]]:
    vehicle_items, vehicle_stats = normalise_vehicles(feed(*vehicles), REFERENCE, T)
    trip_items, trip_stats = normalise_trip_updates(feed(*trips), REFERENCE, T)
    return (
        FeedSnapshot(FeedName.VEHICLE_POSITIONS, NOW, NOW, vehicle_items, vehicle_stats, 7),
        FeedSnapshot(FeedName.TRIP_UPDATES, NOW, NOW, trip_items, trip_stats, 7),
    )


def running_ids(vehicles: list[Any], trips: list[Any]) -> list[str]:
    return [r.trip.trip_id for r in running_trips(*snapshots(vehicles, trips), BRISBANE)]


def test_a_started_trip_with_a_fresh_vehicle_is_running() -> None:
    (running,) = running_trips(*snapshots([vehicle("V1")], [trip_update("T1")]), BRISBANE)

    assert (running.trip.trip_id, running.vehicle.vehicle_id) == ("T1", "V1")


def test_a_trip_that_has_not_started_is_not_running_even_with_a_vehicle() -> None:
    # Seen live: such trips report delays around -27 minutes (vehicle waiting at terminus).
    late_start = trip_update("T1", start_time="09:00:01", stops=(("S1", 1, -1688, None),))

    assert running_ids([vehicle("V1")], [late_start]) == []


def test_a_trip_starting_exactly_now_is_running() -> None:
    assert running_ids([vehicle("V1")], [trip_update("T1", start_time="09:00:00")]) == ["T1"]


def test_a_trip_without_a_vehicle_is_not_running() -> None:
    # Seen live: such trips report a delay of zero about 95 % of the time.
    assert running_ids([], [trip_update("T1", stops=(("S1", 1, 0, 0),))]) == []


def test_a_trip_whose_vehicle_report_is_stale_is_not_running() -> None:
    assert running_ids([vehicle("V1", age_s=91)], [trip_update("T1")]) == []


def test_a_cancelled_trip_is_not_running() -> None:
    assert running_ids([vehicle("V1")], [trip_update("T1", relationship=CANCELED)]) == []


def test_a_trip_unknown_to_the_schedule_is_not_running() -> None:
    assert running_ids([vehicle("V1", trip_id="T404")], [trip_update("T404")]) == []


def test_a_trip_without_a_readable_start_is_not_running() -> None:
    assert running_ids([vehicle("V1")], [trip_update("T1", start_time="")]) == []


def test_a_fresh_vehicle_wins_over_a_stale_one_on_the_same_trip() -> None:
    # Seen live: two vehicle records for one trip (coupled units), one of them stale.
    vehicles = [vehicle("FRESH", age_s=23), vehicle("STALE", age_s=163)]

    (running,) = running_trips(*snapshots(vehicles, [trip_update("T1")]), BRISBANE)

    assert running.vehicle.vehicle_id == "FRESH"


def test_yesterdays_service_running_past_midnight_counts_as_started() -> None:
    # 25:10:00 on the 15th is 01:10 on the 16th: long started by 09:00.
    overnight = trip_update("T1", start_date="20261115", start_time="25:10:00")

    assert running_ids([vehicle("V1")], [overnight]) == ["T1"]


def test_tomorrows_early_trip_has_not_started() -> None:
    tomorrow = trip_update("T1", start_date="20261117", start_time="00:05:00")

    assert running_ids([vehicle("V1")], [tomorrow]) == []


def test_only_running_trips_are_returned_from_a_mixed_feed() -> None:
    vehicles = [vehicle("V1", trip_id="T1"), vehicle("V3", trip_id="T3", age_s=400)]
    trips = [
        trip_update("T1"),
        trip_update("T2", vehicle_id=""),
        trip_update("T3", vehicle_id="V3"),
        trip_update("T4", start_time="10:00:00"),
    ]

    assert running_ids(vehicles, trips) == ["T1"]


def test_service_start_uses_the_local_service_day() -> None:
    start = service_start_epoch(dt.date(2026, 11, 16), 9 * 3600, BRISBANE)

    assert start == NOW
    assert service_start_epoch(dt.date(2026, 11, 15), 33 * 3600, BRISBANE) == NOW
