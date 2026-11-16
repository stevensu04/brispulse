"""Record-level validation, one test per hazard found in the live feeds."""

import datetime as dt
from dataclasses import replace

from google.transit import gtfs_realtime_pb2 as pb

from brispulse.realtime.normalise import (
    normalise_alerts,
    normalise_trip_updates,
    normalise_vehicles,
)
from brispulse.realtime.thresholds import DEFAULT_THRESHOLDS as T
from tests.rt_fixture import (
    CANCELED,
    NOW,
    REFERENCE,
    REPLACEMENT,
    alert,
    feed,
    trip_update,
    vehicle,
)


class TestVehicles:
    def test_a_normal_vehicle(self) -> None:
        vehicles, stats = normalise_vehicles(feed(vehicle("V1", label="1234")), REFERENCE, T)

        (v,) = vehicles
        assert (v.vehicle_id, v.label, v.trip_id, v.route_id, v.mode) == (
            "V1",
            "1234",
            "T1",
            "R1",
            "bus",
        )
        assert (round(v.lat, 2), round(v.lon, 2)) == (-27.47, 153.02)
        assert (v.status, v.stop_id, v.stop_sequence) == ("stopped_at", "S1", 3)
        assert (v.timestamp, v.age_s, v.fresh, v.matched) == (NOW - 10, 10, True, True)
        assert (stats.entity_count, stats.accepted, dict(stats.rejected)) == (1, 1, {})

    def test_freshness_boundary_is_ninety_seconds(self) -> None:
        vehicles, _ = normalise_vehicles(
            feed(vehicle("A", age_s=90), vehicle("B", age_s=91)), REFERENCE, T
        )

        assert {v.vehicle_id: v.fresh for v in vehicles} == {"A": True, "B": False}

    def test_a_stale_vehicle_is_kept_as_last_seen(self) -> None:
        vehicles, stats = normalise_vehicles(feed(vehicle(age_s=600)), REFERENCE, T)

        assert [(v.age_s, v.fresh) for v in vehicles] == [(600, False)]
        assert stats.dropped_stale == 0

    def test_a_vehicle_silent_for_hours_is_dropped_not_rejected(self) -> None:
        # Seen live: a position 9,157 s old inside a feed 43 s old.
        vehicles, stats = normalise_vehicles(
            feed(vehicle("OLD", age_s=9157), vehicle("EDGE", age_s=900)), REFERENCE, T
        )

        assert [v.vehicle_id for v in vehicles] == ["EDGE"]
        assert stats.dropped_stale == 1
        assert dict(stats.rejected) == {}

    def test_timestamps_from_the_future_are_rejected_beyond_the_tolerance(self) -> None:
        vehicles, stats = normalise_vehicles(
            feed(vehicle("OK", timestamp=NOW + 60), vehicle("BAD", timestamp=NOW + 61)),
            REFERENCE,
            T,
        )

        assert [(v.vehicle_id, v.age_s, v.fresh) for v in vehicles] == [("OK", 0, True)]
        assert dict(stats.rejected) == {"bad_timestamp": 1}

    def test_a_missing_timestamp_is_rejected(self) -> None:
        _, stats = normalise_vehicles(feed(vehicle(timestamp=0)), REFERENCE, T)

        assert dict(stats.rejected) == {"bad_timestamp": 1}

    def test_positions_outside_south_east_queensland_are_rejected(self) -> None:
        vehicles, stats = normalise_vehicles(
            feed(
                vehicle("SYDNEY", lat=-33.87, lon=151.21),
                vehicle("NULL_ISLAND", lat=0.0, lon=0.0),
                vehicle("NO_POSITION", lat=None, lon=None),
                vehicle("BRISBANE"),
            ),
            REFERENCE,
            T,
        )

        assert [v.vehicle_id for v in vehicles] == ["BRISBANE"]
        assert dict(stats.rejected) == {"bad_position": 3}

    def test_an_unknown_trip_or_route_is_kept_but_unmatched(self) -> None:
        vehicles, stats = normalise_vehicles(
            feed(
                vehicle("A", trip_id="T404"),
                vehicle("B", route_id="R404"),
                vehicle("C", trip_id="", route_id=""),
                vehicle("D"),
            ),
            REFERENCE,
            T,
        )

        by_id = {v.vehicle_id: v for v in vehicles}
        assert [by_id[k].matched for k in "ABCD"] == [False, False, False, True]
        assert by_id["B"].mode is None
        assert (by_id["C"].trip_id, by_id["C"].route_id) == (None, None)
        assert (stats.accepted, stats.unmatched) == (4, 3)

    def test_a_repeated_vehicle_id_is_rejected(self) -> None:
        vehicles, stats = normalise_vehicles(
            feed(vehicle("V1", age_s=5), vehicle("V1", age_s=50)), REFERENCE, T
        )

        assert [v.age_s for v in vehicles] == [5]
        assert dict(stats.rejected) == {"duplicate_id": 1}

    def test_an_entity_of_another_kind_is_rejected(self) -> None:
        _, stats = normalise_vehicles(feed(alert()), REFERENCE, T)

        assert (stats.entity_count, stats.accepted) == (1, 0)
        assert dict(stats.rejected) == {"not_a_vehicle": 1}

    def test_optional_fields_stay_missing(self) -> None:
        entity = vehicle(stop_id="", stop_sequence=None)
        entity.vehicle.ClearField("current_status")

        (v,), _ = normalise_vehicles(feed(entity), REFERENCE, T)

        assert (v.status, v.stop_id, v.stop_sequence, v.label) == (None, None, None, None)

    def test_limits_come_from_the_thresholds(self) -> None:
        strict = replace(T, vehicle_fresh_s=5, vehicle_drop_s=8)

        vehicles, stats = normalise_vehicles(
            feed(vehicle("A", age_s=6), vehicle("B", age_s=9)), REFERENCE, strict
        )

        assert [(v.vehicle_id, v.fresh) for v in vehicles] == [("A", False)]
        assert stats.dropped_stale == 1


class TestTripUpdates:
    def test_a_normal_trip_update(self) -> None:
        trips, stats = normalise_trip_updates(feed(trip_update()), REFERENCE, T)

        (trip,) = trips
        assert (trip.trip_id, trip.route_id, trip.mode, trip.vehicle_id) == (
            "T1",
            "R1",
            "bus",
            "V1",
        )
        assert trip.start_date == dt.date(2026, 11, 16)
        assert trip.start_time_s == 8 * 3600 + 30 * 60
        assert (trip.relationship, trip.canceled, trip.matched) == ("scheduled", False, True)
        assert (trip.next_stop_delay_s, trip.delay_implausible) == (120, False)
        assert trip.timestamp == NOW - 20
        (prediction,) = trip.predictions
        assert prediction.stop_id == "S1"
        assert prediction.stop_sequence == 3
        assert (prediction.arrival_delay_s, prediction.departure_delay_s) == (120, 130)
        assert prediction.arrival_time == NOW + 420
        assert (stats.accepted, stats.unmatched, stats.canceled) == (1, 0, 0)

    def test_the_delay_is_taken_from_the_first_stop_that_has_one(self) -> None:
        stops = (("S1", 1, None, None), ("S2", 2, None, 45), ("S1", 3, 300, 300))

        (trip,), _ = normalise_trip_updates(feed(trip_update(stops=stops)), REFERENCE, T)

        assert trip.next_stop_delay_s == 45
        assert len(trip.predictions) == 3

    def test_a_trip_without_any_delay_has_none_not_zero(self) -> None:
        (trip,), _ = normalise_trip_updates(
            feed(trip_update(stops=(("S1", 1, None, None),))), REFERENCE, T
        )

        assert trip.next_stop_delay_s is None
        assert trip.delay_implausible is False

    def test_a_trip_without_stop_updates_is_kept(self) -> None:
        (trip,), _ = normalise_trip_updates(feed(trip_update(stops=())), REFERENCE, T)

        assert (trip.predictions, trip.next_stop_delay_s) == ((), None)

    def test_delays_beyond_an_hour_are_flagged_not_dropped(self) -> None:
        # Seen live: -6,588 s and +4,883 s.
        trips, stats = normalise_trip_updates(
            feed(
                trip_update("T1", stops=(("S1", 1, -6588, None),)),
                trip_update("T2", stops=(("S1", 1, 4883, None),)),
                trip_update("T3", stops=(("S1", 1, 3600, None),)),
            ),
            REFERENCE,
            T,
        )

        assert {t.trip_id: t.delay_implausible for t in trips} == {
            "T1": True,
            "T2": True,
            "T3": False,
        }
        assert {t.trip_id: t.next_stop_delay_s for t in trips}["T1"] == -6588
        assert stats.implausible_delays == 2

    def test_cancelled_trips_are_kept_and_counted(self) -> None:
        trips, stats = normalise_trip_updates(
            feed(trip_update("T1", relationship=CANCELED, stops=()), trip_update("T2")),
            REFERENCE,
            T,
        )

        assert {t.trip_id: t.canceled for t in trips} == {"T1": True, "T2": False}
        assert stats.canceled == 1

    def test_replacement_trips_are_ordinary_trips_with_a_label(self) -> None:
        # Seen live: all on rail routes, with vehicles and normal delays.
        (trip,), stats = normalise_trip_updates(
            feed(trip_update("T2", route_id="R2", relationship=REPLACEMENT)), REFERENCE, T
        )

        assert (trip.relationship, trip.canceled, trip.mode, trip.matched) == (
            "replacement",
            False,
            "rail",
            True,
        )
        assert stats.canceled == 0

    def test_an_unknown_trip_is_kept_but_unmatched(self) -> None:
        trips, stats = normalise_trip_updates(
            feed(trip_update("T404"), trip_update("T1", route_id="R404")), REFERENCE, T
        )

        assert [t.matched for t in trips] == [False, False]
        assert stats.unmatched == 2

    def test_missing_and_repeated_trip_ids_are_rejected(self) -> None:
        trips, stats = normalise_trip_updates(
            feed(trip_update(""), trip_update("T1"), trip_update("T1"), vehicle()),
            REFERENCE,
            T,
        )

        assert [t.trip_id for t in trips] == ["T1"]
        assert dict(stats.rejected) == {
            "missing_trip_id": 1,
            "duplicate_trip": 1,
            "not_a_trip_update": 1,
        }

    def test_start_times_past_midnight_and_unreadable_starts(self) -> None:
        trips, _ = normalise_trip_updates(
            feed(
                trip_update("T1", start_date="20261115", start_time="25:10:00"),
                trip_update("T2", start_date="soon", start_time="early"),
                trip_update("T3", start_date="", start_time=""),
            ),
            REFERENCE,
            T,
        )

        by_id = {t.trip_id: t for t in trips}
        assert by_id["T1"].start_date == dt.date(2026, 11, 15)
        assert by_id["T1"].start_time_s == 25 * 3600 + 600
        assert (by_id["T2"].start_date, by_id["T2"].start_time_s) == (None, None)
        assert (by_id["T3"].start_date, by_id["T3"].start_time_s) == (None, None)

    def test_a_trip_update_without_a_vehicle(self) -> None:
        (trip,), _ = normalise_trip_updates(feed(trip_update(vehicle_id="")), REFERENCE, T)

        assert trip.vehicle_id is None


class TestAlerts:
    def test_a_normal_alert(self) -> None:
        alerts, stats = normalise_alerts(feed(alert(stop_ids=("S1",))), REFERENCE)

        (a,) = alerts
        assert (a.alert_id, a.cause, a.effect) == ("A1", "construction", "stop_moved")
        assert (a.header, a.description) == ("Stop moved", "Use the temporary stop.")
        assert (a.route_ids, a.stop_ids) == (("R1",), ("S1",))
        assert (a.unresolved_route_ids, a.unresolved_stop_ids) == ((), ())
        assert a.url is None
        assert (stats.accepted, stats.unmatched) == (1, 0)

    def test_an_alert_is_active_only_inside_one_of_its_periods(self) -> None:
        # Seen live: recurring night works listed as many separate windows.
        periods = ((NOW - 7200, NOW - 3600), (NOW + 3600, NOW + 7200))

        (a,), _ = normalise_alerts(feed(alert(periods=periods)), REFERENCE)

        assert a.is_active(NOW - 5000) is True
        assert a.is_active(NOW) is False
        assert a.is_active(NOW + 3600) is True
        assert a.is_active(NOW + 7200) is True
        assert a.is_active(NOW + 7201) is False

    def test_open_ended_periods(self) -> None:
        alerts, _ = normalise_alerts(
            feed(
                alert("FROM", periods=((NOW - 10, None),)),
                alert("UNTIL", periods=((None, NOW - 10),)),
                alert("ALWAYS", periods=()),
            ),
            REFERENCE,
        )

        assert {a.alert_id: a.is_active(NOW) for a in alerts} == {
            "FROM": True,
            "UNTIL": False,
            "ALWAYS": True,
        }

    def test_an_unknown_stop_is_recorded_and_the_alert_kept(self) -> None:
        # Seen live: 1 of 75 referenced stops was absent from stops.txt.
        (a,), stats = normalise_alerts(
            feed(alert(route_ids=("R1", "R404"), stop_ids=("S1", "S404"))), REFERENCE
        )

        assert (a.route_ids, a.stop_ids) == (("R1", "R404"), ("S1", "S404"))
        assert (a.unresolved_route_ids, a.unresolved_stop_ids) == (("R404",), ("S404",))
        assert stats.unmatched == 1

    def test_repeated_references_are_listed_once(self) -> None:
        (a,), _ = normalise_alerts(feed(alert(route_ids=("R1", "R2", "R1"))), REFERENCE)

        assert a.route_ids == ("R1", "R2")

    def test_english_text_is_preferred_and_missing_text_stays_missing(self) -> None:
        entity = alert(header="Arrêt déplacé", description="", language="fr")
        english = entity.alert.header_text.translation.add()
        english.text, english.language = " Stop moved ", "en"

        (a,), _ = normalise_alerts(feed(entity), REFERENCE)

        assert (a.header, a.description) == ("Stop moved", None)

    def test_unknown_cause_and_effect_default_as_the_specification_says(self) -> None:
        entity = alert()
        entity.alert.ClearField("cause")
        entity.alert.ClearField("effect")

        (a,), _ = normalise_alerts(feed(entity), REFERENCE)

        assert (a.cause, a.effect) == (
            pb.Alert.Cause.Name(pb.Alert.UNKNOWN_CAUSE).lower(),
            pb.Alert.Effect.Name(pb.Alert.UNKNOWN_EFFECT).lower(),
        )

    def test_entities_without_an_alert_or_an_id_are_rejected(self) -> None:
        alerts, stats = normalise_alerts(
            feed(vehicle(), alert(""), alert("A1"), alert("A1")), REFERENCE
        )

        assert [a.alert_id for a in alerts] == ["A1"]
        assert dict(stats.rejected) == {"not_an_alert": 1, "missing_id": 1, "duplicate_id": 1}
