"""Every endpoint's response matches its published schema, in every data condition."""

from typing import Any

import pytest
from pydantic import BaseModel

from brispulse.api.schemas import (
    AlertOut,
    AnalyticsNow,
    Envelope,
    ErrorResponse,
    MetricsData,
    OverviewData,
    RouteDetail,
    RouteSummary,
    StatusData,
    TripDetail,
    VehicleOut,
)
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

ENDPOINTS: list[tuple[str, Any]] = [
    ("/api/v1/status", Envelope[StatusData]),
    ("/api/v1/overview", Envelope[OverviewData]),
    ("/api/v1/vehicles", Envelope[list[VehicleOut]]),
    ("/api/v1/routes", Envelope[list[RouteSummary]]),
    ("/api/v1/routes/R1", Envelope[RouteDetail]),
    ("/api/v1/trips/T1", Envelope[TripDetail]),
    ("/api/v1/alerts", Envelope[list[AlertOut]]),
    ("/api/v1/analytics/now", Envelope[AnalyticsNow]),
    ("/api/v1/meta/metrics", Envelope[MetricsData]),
]


def empty_service() -> Service:
    return Service()


def aged_service() -> Service:
    """All three feeds older than their limits: everything live is unavailable."""
    return service_with_network(now=NOW + 3 * 3600)


def partial_service() -> Service:
    service = Service()
    service.publish(VP, DEFAULT_VEHICLES)
    return service


CONDITIONS = {
    "live": service_with_network,
    "nothing-fetched": empty_service,
    "everything-too-old": aged_service,
    "vehicles-only": partial_service,
}


@pytest.mark.parametrize(("path", "model"), ENDPOINTS, ids=[path for path, _ in ENDPOINTS])
@pytest.mark.parametrize("condition", CONDITIONS)
def test_response_matches_its_schema(path: str, model: type[BaseModel], condition: str) -> None:
    response = CONDITIONS[condition]().get(path)

    assert response.status_code == 200, response.text
    # strict=True: a number where a string is declared (or the reverse) is a failure.
    model.model_validate_json(response.content, strict=True)
    assert set(response.json()) == {"data", "meta"}


def test_openapi_documents_every_endpoint_with_its_envelope() -> None:
    spec = Service().get("/openapi.json").json()

    documented = {
        path.replace("{route_id}", "R1").replace("{trip_id}", "T1") for path in spec["paths"]
    }
    assert documented == {path for path, _ in ENDPOINTS}
    for path, operations in spec["paths"].items():
        schema = operations["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert schema["$ref"].startswith("#/components/schemas/Envelope_"), path
    assert "healthz" not in str(spec["paths"])


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/api/v1/routes/R404", 404, "not_found"),
        ("/api/v1/trips/T404x", 404, "not_found"),
        ("/api/v1/nothing-here", 404, "not_found"),
        ("/api/v1/vehicles?mode=plane", 422, "invalid_request"),
        ("/api/v1/vehicles?bbox=1,2,3", 422, "invalid_request"),
        ("/api/v1/vehicles?bbox=a,b,c,d", 422, "invalid_request"),
        ("/api/v1/vehicles?bbox=153.1,-27.5,153.0,-27.4", 422, "invalid_request"),
        ("/api/v1/alerts?active=maybe", 422, "invalid_request"),
    ],
)
def test_errors_share_one_shape_and_are_never_cached(path: str, status: int, code: str) -> None:
    response = service_with_network().get(path)

    assert response.status_code == status
    body = ErrorResponse.model_validate_json(response.content, strict=True)
    assert body.error.code == code
    assert body.error.message
    assert response.headers["cache-control"] == "no-store"


def test_post_is_refused_in_the_same_error_shape() -> None:
    response = service_with_network().client.post("/api/v1/overview")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_before_the_service_has_started_every_endpoint_says_not_ready() -> None:
    service = Service()
    del service.app.state.runtime

    for path, _ in ENDPOINTS:
        response = service.get(path)
        assert (response.status_code, response.json()["error"]["code"]) == (503, "not_ready"), path


def test_without_a_schedule_only_status_and_definitions_answer() -> None:
    service = Service(reference=None)

    answered = {path: service.get(path).status_code for path, _ in ENDPOINTS}

    assert answered == {
        "/api/v1/status": 200,
        "/api/v1/overview": 200,
        "/api/v1/meta/metrics": 200,
        "/api/v1/vehicles": 503,
        "/api/v1/routes": 503,
        "/api/v1/routes/R1": 503,
        "/api/v1/trips/T1": 503,
        "/api/v1/alerts": 503,
        "/api/v1/analytics/now": 503,
    }
    assert service.get("/api/v1/vehicles").json()["error"]["code"] == "schedule_not_loaded"
    status = service.get("/api/v1/status").json()
    assert status["data"]["static"] is None
    assert status["meta"]["static_version"] is None
    assert "The static schedule has not been imported yet." in status["meta"]["notes"]


def test_an_unexpected_failure_reveals_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(context: object) -> None:
        raise RuntimeError("secret database password is hunter2")

    monkeypatch.setattr("brispulse.api.views.overview", explode)

    response = service_with_network().get("/api/v1/overview")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "An unexpected error occurred."}
    }
    assert "hunter2" not in response.text


def test_feeds_listed_in_meta_are_the_ones_the_endpoint_uses() -> None:
    service = service_with_network()

    used = {path: sorted(service.get(path).json()["meta"]["feeds"]) for path, _ in ENDPOINTS}

    everything = ["alerts", "trip_updates", "vehicle_positions"]
    assert used == {
        "/api/v1/status": everything,
        "/api/v1/overview": everything,
        "/api/v1/vehicles": ["trip_updates", "vehicle_positions"],
        "/api/v1/routes": everything,
        "/api/v1/routes/R1": everything,
        "/api/v1/trips/T1": ["trip_updates", "vehicle_positions"],
        "/api/v1/alerts": ["alerts"],
        "/api/v1/analytics/now": everything,
        "/api/v1/meta/metrics": [],
    }
    # Published defaults, so a client and this suite agree on what was loaded.
    assert (len(DEFAULT_VEHICLES), len(DEFAULT_TRIPS), len(DEFAULT_ALERTS)) == (4, 4, 3)
    assert ALERTS.value == "alerts" and TU.value == "trip_updates"
