"""Unavailable data is null, never zero, and the response says why (architecture §8)."""

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
from tests.rt_fixture import NOW


def meta(service: Service, path: str) -> dict:  # type: ignore[type-arg]
    return service.get(path).json()["meta"]  # type: ignore[no-any-return]


class TestNothingFetchedYet:
    def test_overview_values_are_null(self) -> None:
        body = Service().get("/api/v1/overview").json()

        assert body["data"] == {"vehicles": None, "trips": None, "alerts": None}
        states = {feed: info["state"] for feed, info in body["meta"]["feeds"].items()}
        assert set(states.values()) == {"unavailable"}
        assert all(
            info["source_timestamp"] is None and info["age_seconds"] is None
            for info in body["meta"]["feeds"].values()
        )
        assert (
            "vehicle_positions: no data has been retrieved yet, so its values are null."
            in body["meta"]["notes"]
        )

    def test_lists_are_null_not_empty(self) -> None:
        service = Service()

        assert service.data("/api/v1/vehicles") is None
        assert service.data("/api/v1/alerts") is None

    def test_route_counts_are_null_not_zero(self) -> None:
        routes = Service().data("/api/v1/routes")

        assert [r["route_id"] for r in routes] == ["R1", "R2"]
        for route in routes:
            assert (route["vehicles_fresh"], route["trips_running"], route["alerts_active"]) == (
                None,
                None,
                None,
            )

    def test_route_detail_sections_are_null(self) -> None:
        detail = Service().data("/api/v1/routes/R1")

        assert detail["route"]["long_name"] == "City Loop"
        assert (detail["vehicles"], detail["running_trips"], detail["alerts"]) == (None, None, None)

    def test_a_scheduled_trip_has_no_realtime_section(self) -> None:
        detail = Service().data("/api/v1/trips/T1")

        assert (detail["in_schedule"], detail["headsign"], detail["realtime"]) == (
            True,
            "City",
            None,
        )


class TestAgeing:
    def test_live_data_carries_no_caveat(self) -> None:
        info = meta(service_with_network(now=NOW + 90), "/api/v1/vehicles")

        assert info["feeds"]["vehicle_positions"]["state"] == "live"
        assert info["feeds"]["vehicle_positions"]["age_seconds"] == 90
        assert info["notes"] == []

    def test_delayed_and_stale_data_is_shown_with_a_note(self) -> None:
        for now, state in ((NOW + 91, "delayed"), (NOW + 301, "stale"), (NOW + 900, "stale")):
            service = service_with_network(now=now)
            body = service.get("/api/v1/vehicles").json()

            assert len(body["data"]) == 4
            assert body["meta"]["feeds"]["vehicle_positions"]["state"] == state
            assert (
                f"vehicle_positions: data is {state} ({now - NOW} s old)." in body["meta"]["notes"]
            )

    def test_data_past_the_limit_is_withheld(self) -> None:
        body = service_with_network(now=NOW + 901).get("/api/v1/vehicles").json()

        assert body["data"] is None
        feed = body["meta"]["feeds"]["vehicle_positions"]
        # The timestamp of the last data is still reported, so a user can see how old it is.
        assert (feed["state"], feed["age_seconds"]) == ("unavailable", 901)
        assert feed["source_timestamp"] == "2026-11-16T09:00:00+10:00"
        assert (
            "vehicle_positions: the latest data is 901 s old, beyond the 900 s limit, "
            "so its values are withheld as null." in body["meta"]["notes"]
        )

    def test_alerts_outlive_vehicle_data(self) -> None:
        overview = service_with_network(now=NOW + 3600).data("/api/v1/overview")

        assert overview["vehicles"] is None
        assert overview["trips"] is None
        assert overview["alerts"]["in_feed"] == 3

    def test_times_carry_the_brisbane_offset(self) -> None:
        info = meta(service_with_network(), "/api/v1/overview")

        assert info["generated_at"] == "2026-11-16T09:00:10+10:00"
        assert info["feeds"]["alerts"]["fetched_at"] == "2026-11-16T09:00:05+10:00"


class TestPartialAvailability:
    def test_without_trip_updates_vehicles_show_but_delays_are_null(self) -> None:
        service = Service()
        service.publish(VP, DEFAULT_VEHICLES)

        body = service.get("/api/v1/vehicles").json()
        overview = service.data("/api/v1/overview")

        assert len(body["data"]) == 4
        assert {v["predicted_delay_s"] for v in body["data"]} == {None}
        assert (
            "predicted_delay_s is null for every vehicle: trip updates are unavailable."
            in body["meta"]["notes"]
        )
        assert overview["vehicles"]["fresh"] == 3
        assert overview["trips"] is None

    def test_without_vehicles_a_trip_cannot_be_called_running_or_not(self) -> None:
        service = Service()
        service.publish(TU, DEFAULT_TRIPS)

        trip = service.data("/api/v1/trips/T1")
        overview = service.data("/api/v1/overview")
        routes = service.data("/api/v1/routes")

        assert trip["realtime"]["predicted_delay_s"] == 120
        assert trip["realtime"]["running"] is None
        assert overview["trips"] is None
        assert [r["trips_running"] for r in routes] == [None, None]

    def test_stale_trip_updates_do_not_hide_fresh_alerts(self) -> None:
        service = Service(now=NOW + 1000)
        service.publish(VP, DEFAULT_VEHICLES, timestamp=NOW + 990)
        service.publish(TU, DEFAULT_TRIPS, timestamp=NOW)
        service.publish(ALERTS, DEFAULT_ALERTS, timestamp=NOW + 990)

        routes = {r["route_id"]: r for r in service.data("/api/v1/routes")}

        assert routes["R1"]["alerts_active"] == 1
        assert routes["R1"]["trips_running"] is None
        assert routes["R1"]["vehicles_fresh"] is not None


class TestRealZeros:
    def test_a_route_with_no_vehicles_reports_zero_when_data_is_live(self) -> None:
        service = Service()
        service.publish(VP, DEFAULT_VEHICLES[:1])
        service.publish(TU, DEFAULT_TRIPS[:1])
        service.publish(ALERTS, ())

        routes = {r["route_id"]: r for r in service.data("/api/v1/routes")}

        assert (routes["R2"]["vehicles_fresh"], routes["R2"]["trips_running"]) == (0, 0)
        assert routes["R2"]["alerts_active"] == 0
        assert service.data("/api/v1/alerts") == []
        assert service.data("/api/v1/overview")["alerts"]["active"] == 0

    def test_an_anomalous_feed_is_flagged(self) -> None:
        import dataclasses

        service = service_with_network()
        snapshot = service.live.current.vehicles
        assert snapshot is not None
        service.live.publish(dataclasses.replace(snapshot, anomaly=True))

        info = meta(service, "/api/v1/overview")

        assert info["feeds"]["vehicle_positions"]["anomaly"] is True
        assert (
            "vehicle_positions: far fewer records than usual in the latest data." in info["notes"]
        )
