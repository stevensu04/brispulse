"""Security and caching headers on every kind of response."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brispulse.config import Settings
from brispulse.main import create_app
from brispulse.security import CONTENT_SECURITY_POLICY
from tests.api_fixture import service_with_network


@pytest.fixture
def web_client(tmp_path: Path) -> TestClient:
    (tmp_path / "index.html").write_text("<!doctype html><title>BrisPulse</title>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    settings = Settings(database_url=None, collector_enabled=False, web_dir=str(tmp_path))
    return TestClient(create_app(settings), raise_server_exceptions=False)


def test_api_responses_carry_the_security_headers() -> None:
    response = service_with_network().get("/api/v1/overview")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["strict-transport-security"] == "max-age=31536000"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    # The API's own caching is left as it was.
    assert response.headers["cache-control"] == "public, max-age=10"


def test_errors_carry_them_too() -> None:
    response = service_with_network().get("/api/v1/routes/R404")

    assert response.status_code == 404
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


def test_the_policy_allows_only_this_site_and_the_map_tiles() -> None:
    directives = dict(part.split(" ", 1) for part in CONTENT_SECURITY_POLICY.split("; "))

    assert directives["default-src"] == "'self'"
    assert directives["script-src"] == "'self'"
    assert directives["connect-src"] == "'self' https://tiles.openfreemap.org"
    assert directives["frame-ancestors"] == "'none'"
    assert directives["object-src"] == "'none'"


def test_the_api_documentation_is_left_without_a_policy(web_client: TestClient) -> None:
    assert "content-security-policy" not in web_client.get("/docs").headers
    assert web_client.get("/docs").headers["x-content-type-options"] == "nosniff"


def test_hashed_assets_are_cached_for_a_year_and_the_page_is_revalidated(
    web_client: TestClient,
) -> None:
    asset = web_client.get("/assets/index-abc123.js")
    page = web_client.get("/")

    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert page.headers["cache-control"] == "no-cache"
    assert page.headers["content-security-policy"] == CONTENT_SECURITY_POLICY


def test_a_missing_asset_is_not_cached(web_client: TestClient) -> None:
    response = web_client.get("/assets/gone.js")

    assert response.status_code == 404
    assert response.headers.get("cache-control") != "public, max-age=31536000, immutable"
