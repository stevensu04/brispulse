from pathlib import Path

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


def test_the_built_web_app_is_served_alongside_the_api(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>BrisPulse</title>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('hi')")
    settings = Settings(
        database_url="postgresql://unused/unused", collector_enabled=False, web_dir=str(tmp_path)
    )
    client = TestClient(create_app(settings), raise_server_exceptions=False)

    assert "BrisPulse" in client.get("/").text
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/healthz").json() == {"status": "ok"}
    # The API keeps its own answers, including its JSON errors.
    assert client.get("/api/v1/status").json()["error"]["code"] == "not_ready"
    missing = client.get("/api/v1/nope")
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "not_found")


def test_without_a_web_folder_only_the_api_is_served() -> None:
    client = TestClient(create_app(OFFLINE), raise_server_exceptions=False)

    assert client.get("/").status_code == 404
