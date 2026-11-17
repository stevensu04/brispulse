"""The deployment smoke check, against a scripted server."""

import httpx2

from brispulse.smoke import run_checks

PAGE = '<!doctype html><div id="root"></div>'
HEADERS = {
    "content-security-policy": "default-src 'self'",
    "x-content-type-options": "nosniff",
    "strict-transport-security": "max-age=31536000",
}


def status(state: str) -> dict:  # type: ignore[type-arg]
    return {
        "data": {
            "feeds": {
                name: {"state": state} for name in ("vehicle_positions", "trip_updates", "alerts")
            }
        }
    }


class Server:
    """Answers like a deployment that wakes up after some requests."""

    def __init__(
        self, *, asleep_for: int = 0, live_after: int = 0, headers: dict[str, str] | None = None
    ) -> None:
        self.asleep_for = asleep_for
        self.live_after = live_after
        self.headers = HEADERS if headers is None else headers
        self.calls: dict[str, int] = {}

    def client(self) -> httpx2.Client:
        def handle(request: httpx2.Request) -> httpx2.Response:
            path = request.url.path
            self.calls[path] = self.calls.get(path, 0) + 1
            if path == "/healthz":
                if self.calls[path] <= self.asleep_for:
                    return httpx2.Response(502)
                return httpx2.Response(200, json={"status": "ok"})
            if path == "/":
                return httpx2.Response(200, text=PAGE, headers=self.headers)
            if path == "/api/v1/status":
                live = self.calls[path] > self.live_after
                return httpx2.Response(200, json=status("live" if live else "unavailable"))
            if path == "/api/v1/overview":
                return httpx2.Response(200, json={"data": {"vehicles": {"fresh": 1234}}})
            return httpx2.Response(404)

        return httpx2.Client(transport=httpx2.MockTransport(handle))


def results(server: Server, timeout_s: float = 60.0) -> dict[str, tuple[bool, str]]:
    checks = run_checks(
        server.client(), "https://example.test/", timeout_s=timeout_s, sleep=lambda s: None
    )
    return {check.name: (check.ok, check.detail) for check in checks}


def test_a_healthy_deployment_passes_every_check() -> None:
    found = results(Server())

    assert {name: ok for name, (ok, _) in found.items()} == {
        "process up": True,
        "web app served": True,
        "security headers": True,
        "feeds live": True,
        "overview has data": True,
    }
    assert found["overview has data"][1] == "1234 vehicles reporting"


def test_it_waits_for_a_sleeping_host_and_for_the_feeds() -> None:
    server = Server(asleep_for=5, live_after=3)

    found = results(server)

    assert all(ok for ok, _ in found.values())
    assert server.calls["/healthz"] == 6
    assert server.calls["/api/v1/status"] == 4


def test_a_host_that_never_wakes_fails_and_stops_there() -> None:
    server = Server(asleep_for=10_000)

    found = results(server, timeout_s=0.05)

    assert list(found) == ["process up"]
    assert found["process up"][0] is False


def test_missing_security_headers_are_reported() -> None:
    found = results(Server(headers={"x-content-type-options": "nosniff"}))

    ok, detail = found["security headers"]
    assert ok is False
    assert "content-security-policy" in detail and "strict-transport-security" in detail


def test_feeds_that_never_turn_live_fail() -> None:
    found = results(Server(live_after=10_000), timeout_s=0.05)

    assert found["feeds live"][0] is False
    assert "overview has data" not in found
