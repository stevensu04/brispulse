"""What each endpoint returns for the small hand-made network in ``api_fixture``."""

import datetime as dt
import gzip
from typing import Any

from brispulse.realtime.collector import FetchRecord, Outcome
from tests.api_fixture import (
    ALERTS,
    DEFAULT_ALERTS,
    DEFAULT_TRIPS,
    DEFAULT_VEHICLES,
    TU,
    VP,
    Service,
    service_with_network,
)
from tests.rt_fixture import NOW, REFERENCE, trip_update, vehicle


def by(key: str, items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item[key]: item for item in items}


class TestStatus:
    def test_reports_each_feeds_counts_and_last_attempt(self) -> None:
        service = service_with_network()
        service.live.last_attempts[VP] = FetchRecord(
            feed=VP,
            fetched_at=dt.datetime.fromtimestamp(NOW + 8, dt.UTC),
            duration_ms=300,
            outcome=Outcome.NETWORK_ERROR,
        )

        data = service.data("/api/v1/status")

        vehicles = data["feeds"]["vehicle_positions"]
        assert (vehicles["state"], vehicles["entity_count"], vehicles["accepted"]) == ("live", 4, 4)
        assert (vehicles["unmatched"], vehicles["dropped_stale"], vehicles["rejected"]) == (
            1,
            0,
            {},
        )
        # The last attempt failed, yet the earlier data is still being served as live.
        assert vehicles["last_attempt_outcome"] == "network_error"
        assert vehicles["last_attempt_at"] == "2026-11-16T09:00:08+10:00"
        assert data["feeds"]["alerts"]["last_attempt_outcome"] is None

    def test_reports_the_schedule_in_use_and_the_poll_intervals(self) -> None:
        data = service_with_network().data("/api/v1/status")

        assert data["static"] == {
            "version_id": 7,
            "published_at": "2026-11-13T19:45:24Z",
            "feed_start_date": "2026-11-14",
            "feed_end_date": "2027-01-13",
            "routes": 2,
            "stops": 2,
            "trips": 4,
        }
        assert data["poll_interval_seconds"] == {
            "vehicle_positions": 30.0,
            "trip_updates": 60.0,
            "alerts": 120.0,
        }


class TestOverview:
    def test_counts_for_the_default_network(self) -> None:
        data = service_with_network().data("/api/v1/overview")

        assert data["vehicles"] == {
            "fresh": 3,
            "last_seen": 1,
            "fresh_by_mode": {"bus": 2, "rail": 1},
        }
        assert data["trips"]["running"] == 2
        assert data["trips"]["running_by_mode"] == {"bus": 1, "rail": 1}
        assert data["trips"]["canceled"] == 1
        assert data["alerts"] == {
            "in_feed": 3,
            "active": 2,
            "active_planned_works": 1,
            "active_other": 1,
        }

    def test_two_running_trips_are_too_few_for_a_median(self) -> None:
        delay = service_with_network().data("/api/v1/overview")["trips"]["delay"]

        assert (delay["sample_size"], delay["median_s"], delay["p90_s"]) == (2, None, None)
        assert (delay["early"], delay["within_band"], delay["late"]) == (0, 1, 1)

    def test_delay_summary_with_enough_trips_excludes_implausible_values(self) -> None:
        import dataclasses

        trips = {f"T{n}": "City" for n in range(1, 8)}
        service = Service(reference=dataclasses.replace(REFERENCE, trip_headsigns=trips))
        delays = {"T1": -90, "T2": 0, "T3": 60, "T4": 200, "T5": 310, "T6": 700, "T7": 5000}
        service.publish(VP, tuple(vehicle(f"V{t}", trip_id=t) for t in delays))
        service.publish(
            TU,
            tuple(
                trip_update(t, vehicle_id=f"V{t}", stops=(("S1", 1, d, d),))
                for t, d in delays.items()
            ),
        )

        body = service.get("/api/v1/overview").json()
        delay = body["data"]["trips"]["delay"]

        assert body["data"]["trips"]["running"] == 7
        assert (delay["sample_size"], delay["excluded_implausible"]) == (6, 1)
        assert (delay["median_s"], delay["p90_s"]) == (60, 700)
        assert (delay["early"], delay["within_band"], delay["late"]) == (1, 3, 2)
        assert body["data"]["trips"]["delay_by_mode"]["bus"] == delay
        assert any("not on-time performance" in note for note in body["meta"]["notes"])


class TestVehicles:
    def test_each_vehicle_is_named_and_placed(self) -> None:
        vehicles = by("vehicle_id", service_with_network().data("/api/v1/vehicles"))

        v1 = vehicles["V1"]
        assert (v1["label"], v1["mode"], v1["route_id"], v1["route_short_name"]) == (
            "1001",
            "bus",
            "R1",
            "100",
        )
        assert (v1["trip_id"], v1["headsign"], v1["status"]) == ("T1", "City", "stopped_at")
        assert v1["stop"] == {"stop_id": "S1", "name": "First Street"}
        assert v1["reported_at"] == "2026-11-16T08:59:50+10:00"
        assert (v1["fresh"], v1["matched"]) == (True, True)

    def test_delay_is_given_only_for_vehicles_on_running_trips(self) -> None:
        vehicles = by("vehicle_id", service_with_network().data("/api/v1/vehicles"))

        assert {v: vehicles[v]["predicted_delay_s"] for v in vehicles} == {
            "V1": 120,
            "V2": 400,
            # T3's vehicle is stale, so the trip is not running and its "0" is not shown.
            "V3": None,
            "V4": None,
        }

    def test_stale_and_unmatched_vehicles_are_marked(self) -> None:
        vehicles = by("vehicle_id", service_with_network().data("/api/v1/vehicles"))

        assert (vehicles["V3"]["fresh"], vehicles["V3"]["matched"]) == (False, True)
        assert (vehicles["V4"]["fresh"], vehicles["V4"]["matched"]) == (True, False)
        assert vehicles["V4"]["headsign"] is None
        # A stop the schedule does not know keeps its ID and gets no invented name.
        assert vehicles["V4"]["stop"] == {"stop_id": "S404", "name": None}

    def test_filters(self) -> None:
        service = service_with_network()

        def ids(query: str) -> list[str]:
            return sorted(v["vehicle_id"] for v in service.data(f"/api/v1/vehicles?{query}"))

        assert ids("mode=rail") == ["V2"]
        assert ids("mode=ferry") == []
        assert ids("route_id=R1") == ["V1", "V3", "V4"]
        assert ids("fresh_only=true") == ["V1", "V2", "V4"]
        assert ids("bbox=153.05,-27.65,153.15,-27.55") == ["V2"]
        assert ids("route_id=R1&fresh_only=true&mode=bus") == ["V1", "V4"]


class TestAlerts:
    def test_active_alerts_come_first(self) -> None:
        alerts = service_with_network().data("/api/v1/alerts")

        assert [(a["alert_id"], a["active"], a["planned_works"]) for a in alerts] == [
            ("A1", True, True),
            ("A3", True, False),
            ("A2", False, True),
        ]

    def test_an_alert_carries_its_text_periods_routes_and_stops(self) -> None:
        alerts = by("alert_id", service_with_network().data("/api/v1/alerts"))

        a1 = alerts["A1"]
        assert (a1["cause"], a1["effect"]) == ("construction", "stop_moved")
        assert (a1["header"], a1["description"]) == ("Stop moved", "Use the temporary stop.")
        assert a1["active_periods"] == [
            {"start": "2026-11-16T08:00:00+10:00", "end": "2026-11-16T10:00:00+10:00"}
        ]
        assert a1["routes"] == [
            {"route_id": "R1", "short_name": "100", "long_name": "City Loop", "mode": "bus"}
        ]
        assert a1["stops"] == [{"stop_id": "S1", "name": "First Street"}]
        assert alerts["A3"]["stops"] == [{"stop_id": "S404", "name": None}]

    def test_filters(self) -> None:
        service = service_with_network()

        def ids(query: str) -> list[str]:
            return [a["alert_id"] for a in service.data(f"/api/v1/alerts?{query}")]

        assert ids("active=true") == ["A1", "A3"]
        assert ids("active=false") == ["A2"]
        assert ids("route_id=R2") == ["A3", "A2"]
        assert ids("stop_id=S1") == ["A1"]
        assert ids("route_id=R2&active=true") == ["A3"]

    def test_activity_follows_the_clock(self) -> None:
        later = service_with_network(now=NOW + 3600 + 60)
        later.publish(ALERTS, DEFAULT_ALERTS, timestamp=NOW + 3600)

        alerts = by("alert_id", later.data("/api/v1/alerts"))

        # A1's and A3's periods have just ended; A2's has just begun.
        assert {k: a["active"] for k, a in alerts.items()} == {"A1": False, "A2": True, "A3": False}


class TestRoutes:
    def test_routes_with_live_counts(self) -> None:
        routes = by("route_id", service_with_network().data("/api/v1/routes"))

        assert routes["R1"] == {
            "route_id": "R1",
            "short_name": "100",
            "long_name": "City Loop",
            "mode": "bus",
            "color": "00FF00",
            "text_color": "000000",
            # V1 and the unmatched V4 are fresh on R1; only T1 is running.
            "vehicles_fresh": 2,
            "trips_running": 1,
            "alerts_active": 1,
        }
        assert (routes["R2"]["vehicles_fresh"], routes["R2"]["trips_running"]) == (1, 1)
        assert routes["R2"]["alerts_active"] == 1

    def test_mode_filter(self) -> None:
        service = service_with_network()

        assert [r["route_id"] for r in service.data("/api/v1/routes?mode=rail")] == ["R2"]
        assert service.data("/api/v1/routes?mode=tram") == []

    def test_route_detail(self) -> None:
        detail = service_with_network().data("/api/v1/routes/R1")

        assert detail["route"]["trips_running"] == 1
        assert sorted(v["vehicle_id"] for v in detail["vehicles"]) == ["V1", "V3", "V4"]
        assert [a["alert_id"] for a in detail["alerts"]] == ["A1"]
        assert detail["running_trips"] == [
            {
                "trip_id": "T1",
                "headsign": "City",
                "relationship": "scheduled",
                "scheduled_start": "2026-11-16T08:30:00+10:00",
                "vehicle_id": "V1",
                "predicted_delay_s": 120,
                "delay_implausible": False,
                "next_stop": {"stop_id": "S1", "name": "First Street"},
            }
        ]


class TestTrips:
    def test_a_running_trip_with_its_upcoming_stops(self) -> None:
        trip = service_with_network().data("/api/v1/trips/T1")

        assert (trip["trip_id"], trip["in_schedule"], trip["headsign"]) == ("T1", True, "City")
        assert trip["route"]["short_name"] == "100"
        realtime = trip["realtime"]
        assert (realtime["running"], realtime["relationship"], realtime["vehicle_id"]) == (
            True,
            "scheduled",
            "V1",
        )
        assert realtime["scheduled_start"] == "2026-11-16T08:30:00+10:00"
        assert realtime["updated_at"] == "2026-11-16T08:59:40+10:00"
        assert (realtime["predicted_delay_s"], realtime["delay_implausible"]) == (120, False)
        assert realtime["stops"] == [
            {
                "stop": {"stop_id": "S1", "name": "First Street"},
                "stop_sequence": 3,
                "arrival_time": "2026-11-16T09:07:00+10:00",
                "arrival_delay_s": 120,
                "departure_time": "2026-11-16T09:07:10+10:00",
                "departure_delay_s": 130,
            },
            {
                "stop": {"stop_id": "S2", "name": "Second Street"},
                "stop_sequence": 4,
                "arrival_time": "2026-11-16T09:06:50+10:00",
                "arrival_delay_s": 110,
                "departure_time": "2026-11-16T09:06:50+10:00",
                "departure_delay_s": 110,
            },
        ]

    def test_the_vehicle_comes_from_the_vehicle_feed_when_the_trip_update_names_none(
        self,
    ) -> None:
        # Seen live: a running replacement rail trip whose trip update had no vehicle.
        service = Service()
        service.publish(VP, DEFAULT_VEHICLES)
        service.publish(TU, (trip_update("T1", vehicle_id=""),))

        (brief,) = service.data("/api/v1/routes/R1")["running_trips"]
        detail = service.data("/api/v1/trips/T1")["realtime"]

        assert brief["vehicle_id"] == "V1"
        assert (detail["running"], detail["vehicle_id"]) == (True, "V1")

    def test_a_trip_that_is_not_running(self) -> None:
        service = service_with_network()

        assert service.data("/api/v1/trips/T3")["realtime"]["running"] is False
        cancelled = service.data("/api/v1/trips/T4")["realtime"]
        assert (cancelled["relationship"], cancelled["running"]) == ("canceled", False)
        assert (cancelled["predicted_delay_s"], cancelled["stops"]) == (None, [])

    def test_a_scheduled_trip_with_no_realtime_data_says_so(self) -> None:
        service = Service()
        service.publish(VP, DEFAULT_VEHICLES)
        service.publish(TU, DEFAULT_TRIPS[:1])

        body = service.get("/api/v1/trips/T2").json()

        assert body["data"]["in_schedule"] is True
        assert body["data"]["realtime"] is None
        assert body["data"]["route"] is None
        assert (
            "This trip is in the schedule but has no real-time data right now."
            in body["meta"]["notes"]
        )

    def test_a_realtime_trip_missing_from_the_schedule_is_shown_as_such(self) -> None:
        service = service_with_network()
        service.publish(TU, (trip_update("T404", vehicle_id="V4"),))

        trip = service.data("/api/v1/trips/T404")

        assert (trip["in_schedule"], trip["headsign"]) == (False, None)
        # Not in the schedule, so it cannot count as running even with a fresh vehicle.
        assert trip["realtime"]["running"] is False


class TestCaching:
    def test_live_responses_are_cacheable_briefly(self) -> None:
        response = service_with_network().get("/api/v1/vehicles")

        assert response.headers["cache-control"] == "public, max-age=10"
        assert response.headers["etag"].startswith('W/"')

    def test_definitions_are_cacheable_for_longer(self) -> None:
        response = service_with_network().get("/api/v1/meta/metrics")

        assert response.headers["cache-control"] == "public, max-age=300"

    def test_an_unchanged_resource_answers_304(self) -> None:
        service = service_with_network()
        etag = service.get("/api/v1/vehicles").headers["etag"]
        service.now += 5

        response = service.get("/api/v1/vehicles", **{"If-None-Match": etag})

        assert response.status_code == 304
        assert response.content == b""
        assert response.headers["etag"] == etag

    def test_new_data_changes_the_etag(self) -> None:
        service = service_with_network()
        etag = service.get("/api/v1/vehicles").headers["etag"]
        service.publish(VP, DEFAULT_VEHICLES, timestamp=NOW + 5)

        response = service.get("/api/v1/vehicles", **{"If-None-Match": etag})

        assert response.status_code == 200
        assert response.headers["etag"] != etag

    def test_a_change_of_freshness_state_changes_the_etag(self) -> None:
        service = service_with_network()
        etag = service.get("/api/v1/vehicles").headers["etag"]
        service.now = NOW + 120

        response = service.get("/api/v1/vehicles", **{"If-None-Match": etag})

        assert response.status_code == 200
        assert response.json()["meta"]["feeds"]["vehicle_positions"]["state"] == "delayed"

    def test_different_queries_have_different_etags(self) -> None:
        service = service_with_network()

        tags = {
            service.get(f"/api/v1/vehicles{q}").headers["etag"]
            for q in ("", "?mode=bus", "?mode=rail")
        }

        assert len(tags) == 3

    def test_large_responses_are_compressed_on_request(self) -> None:
        service = Service()
        fleet = tuple(vehicle(f"V{n}", trip_id="T1") for n in range(200))
        service.publish(VP, fleet)
        service.publish(TU, DEFAULT_TRIPS)

        raw = service.client.build_request(
            "GET", "/api/v1/vehicles", headers={"Accept-Encoding": "gzip"}
        )
        response = service.client.send(raw, stream=True)
        compressed = b"".join(response.iter_raw())

        assert response.headers["content-encoding"] == "gzip"
        assert len(gzip.decompress(compressed)) > 5 * len(compressed)


class TestMetricDefinitions:
    def test_publishes_definitions_limits_and_attribution(self) -> None:
        data = service_with_network().data("/api/v1/meta/metrics")

        assert [m["name"] for m in data["metrics"]] == [
            "Fresh vehicles",
            "Running trips",
            "Predicted delay",
            "Active alerts",
        ]
        assert all(m["definition"] and m["source"] and m["limitations"] for m in data["metrics"])
        assert data["thresholds"] == {
            "vehicle_fresh_s": 90,
            "vehicle_drop_s": 900,
            "delay_early_s": 60,
            "delay_late_s": 300,
            "delay_plausible_s": 3600,
            "min_sample": 5,
        }
        assert data["freshness_limits_seconds"]["alerts"] == {
            "live": 600,
            "delayed": 1800,
            "stale": 7200,
        }
        assert "State of Queensland" in data["attribution"]
        assert "not affiliated" in data["disclaimer"]
        predicted = data["metrics"][2]
        assert (
            "not" in predicted["limitations"] and "on-time performance" in predicted["limitations"]
        )
