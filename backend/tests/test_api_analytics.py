"""The live analytics endpoint (M4, reduced to what needs no history)."""

import dataclasses

from tests.api_fixture import (
    ALERTS,
    DEFAULT_ALERTS,
    DEFAULT_VEHICLES,
    TU,
    VP,
    Service,
    service_with_network,
)
from tests.rt_fixture import REFERENCE, trip_update, vehicle

PATH = "/api/v1/analytics/now"


def test_late_trips_by_route_for_the_default_network() -> None:
    delays = service_with_network().data(PATH)["delays"]

    # T1 (bus R1) is 120 s late: within band. T2 (rail R2) is 400 s late.
    assert (delays["trips_counted"], delays["routes_with_running_trips"]) == (2, 2)
    assert delays["routes_with_late_trips"] == 1
    assert delays["late_routes"] == [
        {
            "route": {
                "route_id": "R2",
                "short_name": "BNSH",
                "long_name": "Northern Line",
                "mode": "rail",
            },
            "running": 1,
            "late": 1,
            "early": 0,
            "worst_delay_s": 400,
        }
    ]


def test_routes_are_ranked_by_late_trips_then_worst_delay() -> None:
    trips = {f"T{n}": "City" for n in range(1, 8)}
    service = Service(reference=dataclasses.replace(REFERENCE, trip_headsigns=trips))
    plan = {
        "T1": ("R1", 400),
        "T2": ("R1", 900),
        "T3": ("R1", -120),
        "T4": ("R2", 700),
        "T5": ("R2", 1200),
        "T6": ("R2", 30),
        "T7": ("R1", 5000),  # implausible: left out
    }
    service.publish(
        VP, tuple(vehicle(f"V{t}", trip_id=t, route_id=r) for t, (r, _) in plan.items())
    )
    service.publish(
        TU,
        tuple(
            trip_update(t, route_id=r, vehicle_id=f"V{t}", stops=(("S1", 1, d, d),))
            for t, (r, d) in plan.items()
        ),
    )

    delays = service.data(PATH)["delays"]

    assert delays["trips_counted"] == 6
    ranked = [
        (row["route"]["route_id"], row["late"], row["early"], row["worst_delay_s"])
        for row in delays["late_routes"]
    ]
    # Both routes have two late trips; R2's worst delay is larger, so it comes first.
    assert ranked == [("R2", 2, 0, 1200), ("R1", 2, 1, 900)]


def test_alerts_by_effect_cause_and_route() -> None:
    alerts = service_with_network().data(PATH)["alerts"]

    # A1 and A3 are active; A2 starts in an hour.
    assert alerts["active"] == 2
    assert alerts["by_effect"] == {"stop_moved": 1, "significant_delays": 1}
    assert alerts["by_cause"] == {"construction": 1, "other_cause": 1}
    assert [
        (r["route"]["route_id"], r["active_alerts"]) for r in alerts["routes_most_affected"]
    ] == [
        ("R1", 1),
        ("R2", 1),
    ]


def test_no_running_trips_gives_empty_lists_not_null() -> None:
    service = Service()
    service.publish(VP, ())
    service.publish(TU, ())
    service.publish(ALERTS, ())

    data = service.data(PATH)

    # Live feeds that are simply empty: real zeros.
    assert data["delays"] == {
        "trips_counted": 0,
        "routes_with_running_trips": 0,
        "routes_with_late_trips": 0,
        "late_routes": [],
    }
    assert data["alerts"] == {
        "active": 0,
        "by_effect": {},
        "by_cause": {},
        "routes_most_affected": [],
    }


def test_unavailable_feeds_give_null_sections_with_notes() -> None:
    service = Service()
    service.publish(VP, DEFAULT_VEHICLES)

    body = service.get(PATH).json()

    assert body["data"] == {"delays": None, "alerts": None}
    assert (
        "alerts: no data has been retrieved yet, so its values are null." in body["meta"]["notes"]
    )


def test_alerts_survive_when_trip_data_is_missing() -> None:
    service = Service()
    service.publish(ALERTS, DEFAULT_ALERTS)

    data = service.data(PATH)

    assert data["delays"] is None
    assert data["alerts"]["active"] == 2


def test_the_note_says_this_is_a_moment_not_a_trend() -> None:
    notes = service_with_network().get(PATH).json()["meta"]["notes"]

    assert any("this deployment keeps no history" in note for note in notes)
