from fastapi.testclient import TestClient

from brispulse.config import Settings
from brispulse.main import create_app

OFFLINE = Settings(database_url="postgresql://unused/unused", collector_enabled=False)


def test_healthz_reports_liveness() -> None:
    response = TestClient(create_app(OFFLINE)).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_app_starts_and_stops_without_the_collector() -> None:
    with TestClient(create_app(OFFLINE)) as client:
        assert client.get("/healthz").status_code == 200


def test_importing_the_app_needs_no_configuration() -> None:
    # The module-level ``app`` must be importable in an empty environment; settings
    # are only read when the service starts.
    import brispulse.main

    assert brispulse.main.app.title == "BrisPulse"
