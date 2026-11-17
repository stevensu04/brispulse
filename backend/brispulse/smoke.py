"""Checks a running BrisPulse deployment from the outside (M5).

    python -m brispulse.smoke https://brispulse.onrender.com

Waits for a sleeping host to wake, then checks that the process is up, the web app is
served, all three feeds turn live, the overview has data, and the security headers are
present. Prints one line per check and exits 1 if any fails.
"""

import argparse
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx2

from brispulse import __version__


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    ok: bool
    detail: str


def _wait_for_health(
    client: httpx2.Client, base: str, deadline: float, sleep: Callable[[float], None]
) -> Check:
    started = time.monotonic()
    last = "no answer"
    while time.monotonic() < deadline:
        try:
            response = client.get(f"{base}/healthz")
            if response.status_code == 200 and response.json() == {"status": "ok"}:
                return Check(
                    "process up",
                    True,
                    f"/healthz answered after {time.monotonic() - started:.1f} s",
                )
            last = f"HTTP {response.status_code}"
        except (httpx2.HTTPError, ValueError) as exc:
            last = type(exc).__name__
        sleep(2.0)
    return Check("process up", False, f"/healthz not ok before the deadline ({last})")


def _wait_for_live(
    client: httpx2.Client, base: str, deadline: float, sleep: Callable[[float], None]
) -> Check:
    started = time.monotonic()
    states: dict[str, str] = {}
    while time.monotonic() < deadline:
        try:
            feeds = client.get(f"{base}/api/v1/status").json()["data"]["feeds"]
            states = {name: feed["state"] for name, feed in feeds.items()}
            if states and all(state == "live" for state in states.values()):
                return Check(
                    "feeds live",
                    True,
                    f"all {len(states)} live after {time.monotonic() - started:.1f} s",
                )
        except (httpx2.HTTPError, ValueError, KeyError, TypeError):
            pass
        sleep(3.0)
    return Check("feeds live", False, f"not all live before the deadline: {states or 'no status'}")


def run_checks(
    client: httpx2.Client,
    base: str,
    *,
    timeout_s: float = 240.0,
    sleep: Callable[[float], None] = time.sleep,
) -> list[Check]:
    base = base.rstrip("/")
    deadline = time.monotonic() + timeout_s
    checks = [_wait_for_health(client, base, deadline, sleep)]
    if not checks[0].ok:
        return checks

    page = client.get(f"{base}/")
    checks.append(
        Check(
            "web app served",
            page.status_code == 200 and 'id="root"' in page.text,
            f"HTTP {page.status_code}",
        )
    )
    headers = page.headers
    missing = [
        name
        for name in (
            "content-security-policy",
            "x-content-type-options",
            "strict-transport-security",
        )
        if name not in headers
    ]
    checks.append(
        Check(
            "security headers", not missing, "all present" if not missing else f"missing {missing}"
        )
    )

    live = _wait_for_live(client, base, deadline, sleep)
    checks.append(live)
    if live.ok:
        overview = client.get(f"{base}/api/v1/overview").json()["data"]
        vehicles = (overview or {}).get("vehicles")
        checks.append(
            Check(
                "overview has data",
                vehicles is not None,
                f"{vehicles['fresh']} vehicles reporting" if vehicles else "vehicles is null",
            )
        )
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m brispulse.smoke")
    parser.add_argument("base_url", help="for example https://brispulse.onrender.com")
    parser.add_argument("--timeout", type=float, default=240.0, help="seconds to wait in total")
    args = parser.parse_args(argv)
    headers = {"User-Agent": f"BrisPulse-smoke/{__version__}"}
    with httpx2.Client(timeout=60.0, headers=headers, follow_redirects=True) as client:
        checks = run_checks(client, args.base_url, timeout_s=args.timeout)
    for check in checks:
        print(f"{'PASS' if check.ok else 'FAIL'}  {check.name}: {check.detail}")
    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
