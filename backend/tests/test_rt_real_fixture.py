"""The collector's code against a sample of real TransLink data.

The synthetic tests prove each rule in isolation. This one proves the rules hold on
what TransLink actually publishes, and pins the result so a change in behaviour shows.
See ``tests/fixtures/README.md`` for what the sample contains and its attribution.
"""

import json
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from brispulse.realtime import decode
from brispulse.realtime.model import Alert, FeedName, FeedSnapshot, TripState, Vehicle
from brispulse.realtime.normalise import (
    normalise_alerts,
    normalise_trip_updates,
    normalise_vehicles,
)
from brispulse.realtime.populations import running_trips
from brispulse.realtime.reference import Reference, RouteInfo, StopInfo
from brispulse.realtime.thresholds import DEFAULT_THRESHOLDS

FIXTURE = Path(__file__).parent / "fixtures" / "translink_2026-11-16_0903"
# The feed header's timestamp: Monday 2026-11-16 09:03:20 in Brisbane.
SOURCE_TIMESTAMP = 1_794_783_800


@pytest.fixture(scope="module")
def reference() -> Reference:
    data = json.loads((FIXTURE / "reference.json").read_text())
    return Reference(
        version_id=1,
        routes={
            route_id: RouteInfo(None, None, mode, None, None)
            for route_id, mode in data["route_modes"].items()
        },
        trip_headsigns=dict.fromkeys(data["trip_ids"]),
        stops={stop_id: StopInfo(stop_id, 0.0, 0.0) for stop_id in data["stop_ids"]},
    )


@pytest.fixture(scope="module")
def vehicles(reference: Reference) -> FeedSnapshot[Vehicle]:
    message = decode.decode_feed((FIXTURE / "vehicle_positions.pb").read_bytes())
    items, stats = normalise_vehicles(message, reference, DEFAULT_THRESHOLDS)
    return FeedSnapshot(FeedName.VEHICLE_POSITIONS, message.header.timestamp, 0, items, stats, 1)


@pytest.fixture(scope="module")
def trips(reference: Reference) -> FeedSnapshot[TripState]:
    message = decode.decode_feed((FIXTURE / "trip_updates.pb").read_bytes())
    items, stats = normalise_trip_updates(message, reference, DEFAULT_THRESHOLDS)
    return FeedSnapshot(FeedName.TRIP_UPDATES, message.header.timestamp, 0, items, stats, 1)


@pytest.fixture(scope="module")
def alerts(reference: Reference) -> FeedSnapshot[Alert]:
    message = decode.decode_feed((FIXTURE / "alerts.pb").read_bytes())
    items, stats = normalise_alerts(message, reference)
    return FeedSnapshot(FeedName.ALERTS, message.header.timestamp, 0, items, stats, 1)


def test_real_feeds_decode_as_version_2(
    vehicles: FeedSnapshot[Vehicle], trips: FeedSnapshot[TripState], alerts: FeedSnapshot[Alert]
) -> None:
    # The three feeds were fetched seconds apart, so their timestamps differ slightly.
    assert trips.source_timestamp == SOURCE_TIMESTAMP
    assert vehicles.source_timestamp == SOURCE_TIMESTAMP + 10
    assert alerts.source_timestamp == SOURCE_TIMESTAMP + 20


def test_no_real_record_is_rejected_or_unmatched(
    vehicles: FeedSnapshot[Vehicle], trips: FeedSnapshot[TripState], alerts: FeedSnapshot[Alert]
) -> None:
    for snapshot in (vehicles, trips, alerts):
        assert dict(snapshot.stats.rejected) == {}
    assert (vehicles.stats.unmatched, trips.stats.unmatched) == (0, 0)


def test_real_vehicles(vehicles: FeedSnapshot[Vehicle]) -> None:
    stats = vehicles.stats
    assert (stats.entity_count, stats.accepted, stats.dropped_stale) == (100, 93, 7)
    assert sum(v.fresh for v in vehicles.items) == 85
    assert Counter(v.mode for v in vehicles.items) == {"bus": 85, "rail": 4, "ferry": 4}
    assert all(-28.5 < v.lat < -25.9 and 152.0 < v.lon < 153.7 for v in vehicles.items)


def test_real_trip_updates(trips: FeedSnapshot[TripState]) -> None:
    stats = trips.stats
    assert (stats.entity_count, stats.accepted) == (129, 129)
    assert (stats.canceled, stats.implausible_delays) == (1, 1)
    assert Counter(t.relationship for t in trips.items) == {
        "scheduled": 122,
        "replacement": 6,
        "canceled": 1,
    }
    assert sum(len(t.predictions) for t in trips.items) == 2288
    # Every real trip states its start, which the running-trip rule depends on.
    assert all(t.start_date is not None and t.start_time_s is not None for t in trips.items)
    # The cancelled trip carries no prediction, and so no delay: None, never zero.
    (canceled,) = [t for t in trips.items if t.canceled]
    assert (canceled.predictions, canceled.next_stop_delay_s) == ((), None)


def test_real_alerts(alerts: FeedSnapshot[Alert]) -> None:
    assert (alerts.stats.entity_count, alerts.stats.accepted) == (65, 65)
    # Counting every alert in the feed would overstate active alerts by half.
    assert sum(a.is_active(alerts.source_timestamp) for a in alerts.items) == 44
    assert sum(len(a.active_periods) > 1 for a in alerts.items) == 9
    assert Counter(a.cause for a in alerts.items).most_common(2) == [
        ("construction", 33),
        ("maintenance", 19),
    ]
    assert all(a.header for a in alerts.items)
    # One alert names a stop that is absent from the static schedule.
    assert alerts.stats.unmatched == 1
    assert [(a.alert_id, a.unresolved_stop_ids) for a in alerts.items if a.unresolved_stop_ids] == [
        ("906416", ("316056",))
    ]


def test_only_half_of_the_real_trips_are_running(
    vehicles: FeedSnapshot[Vehicle], trips: FeedSnapshot[TripState]
) -> None:
    running = running_trips(vehicles, trips, ZoneInfo("Australia/Brisbane"))

    assert len(running) == 65
    assert Counter(r.trip.mode for r in running) == {"bus": 62, "ferry": 2, "rail": 1}
    # A replacement rail trip with a live vehicle counts as running.
    assert Counter(r.trip.relationship for r in running) == {"scheduled": 64, "replacement": 1}
    assert all(r.vehicle.fresh and r.trip.next_stop_delay_s is not None for r in running)

    delays = sorted(r.trip.next_stop_delay_s or 0 for r in running)
    assert (delays[0], delays[len(delays) // 2], delays[-1]) == (-698, 123, 1515)

    # The trips left out are the ones that would distort a delay figure: more than
    # half of them report a delay of exactly zero.
    running_ids = {r.trip.trip_id for r in running}
    excluded = [t for t in trips.items if t.trip_id not in running_ids]
    assert len(excluded) == 64
    assert sum(t.next_stop_delay_s == 0 for t in excluded) == 37
