"""The collector's behaviour on each kind of response, without a network or database."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx2
import pytest

from brispulse.config import Settings
from brispulse.realtime.collector import Collector, FetchRecord, LiveStateHolder, Outcome
from brispulse.realtime.model import FeedName
from brispulse.realtime.reference import Reference
from tests.rt_fixture import NOW, REFERENCE, alert, feed_bytes, trip_update, vehicle

pytestmark = pytest.mark.anyio

VP = FeedName.VEHICLE_POSITIONS
LAST_MODIFIED = "Sun, 15 Nov 2026 23:00:00 GMT"


def ok(body: bytes, last_modified: str = LAST_MODIFIED) -> httpx2.Response:
    return httpx2.Response(200, content=body, headers={"Last-Modified": last_modified})


@dataclass
class Harness:
    """A collector wired to a scripted server, a settable clock and an in-memory log."""

    replies: list[httpx2.Response | Exception] = field(default_factory=list)
    requests: list[httpx2.Request] = field(default_factory=list)
    records: list[FetchRecord] = field(default_factory=list)
    now: float = NOW + 5
    reference: Reference | None = REFERENCE
    record_fetch: Callable[[FetchRecord], None] | None = None

    def __post_init__(self) -> None:
        def handle(request: httpx2.Request) -> httpx2.Response:
            self.requests.append(request)
            reply = self.replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply

        self.state = LiveStateHolder()
        self.collector = Collector(
            Settings(
                database_url="postgresql://unused/unused", translink_base_url="https://tl.test"
            ),
            httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
            self.state,
            lambda: self.reference,
            self.record_fetch or self.records.append,
            clock=lambda: self.now,
        )

    async def poll(self, reply: httpx2.Response | Exception, feed: FeedName = VP) -> FetchRecord:
        self.replies.append(reply)
        return await self.collector.poll_once(feed)


async def test_a_good_response_becomes_the_live_snapshot() -> None:
    harness = Harness()

    record = await harness.poll(ok(feed_bytes(vehicle("V1"), vehicle("V2", lat=0.0, lon=0.0))))

    assert record.outcome is Outcome.OK
    assert (record.http_status, record.entity_count, record.accepted_count) == (200, 2, 1)
    assert record.rejected == {"bad_position": 1}
    assert record.source_timestamp is not None
    assert int(record.source_timestamp.timestamp()) == NOW
    assert int(record.fetched_at.timestamp()) == NOW + 5
    assert record.static_version_id == REFERENCE.version_id
    assert record.body_bytes is not None and record.body_bytes > 0
    snapshot = harness.state.current.vehicles
    assert snapshot is not None
    assert [v.vehicle_id for v in snapshot.items] == ["V1"]
    assert (snapshot.source_timestamp, snapshot.fetched_at) == (NOW, NOW + 5)
    assert snapshot.anomaly is False
    assert harness.records == [record]


@pytest.mark.parametrize(
    ("feed", "body", "path", "slot"),
    [
        (FeedName.VEHICLE_POSITIONS, feed_bytes(vehicle()), "VehiclePositions", "vehicles"),
        (FeedName.TRIP_UPDATES, feed_bytes(trip_update()), "TripUpdates", "trip_updates"),
        (FeedName.ALERTS, feed_bytes(alert()), "Alerts", "alerts"),
    ],
)
async def test_each_feed_has_its_own_url_and_slot(
    feed: FeedName, body: bytes, path: str, slot: str
) -> None:
    harness = Harness()

    record = await harness.poll(ok(body), feed)

    assert record.outcome is Outcome.OK
    assert str(harness.requests[0].url) == f"https://tl.test/api/realtime/SEQ/{path}"
    slots = {
        name: getattr(harness.state.current, name)
        for name in ("vehicles", "trip_updates", "alerts")
    }
    assert [name for name, value in slots.items() if value is not None] == [slot]
    assert len(slots[slot].items) == 1


async def test_later_polls_are_conditional_and_304_keeps_the_snapshot() -> None:
    harness = Harness()
    await harness.poll(ok(feed_bytes(vehicle())))
    before = harness.state.current.vehicles

    record = await harness.poll(httpx2.Response(304))

    assert "if-modified-since" not in harness.requests[0].headers
    assert harness.requests[1].headers["if-modified-since"] == LAST_MODIFIED
    assert (record.outcome, record.http_status) == (Outcome.NOT_MODIFIED, 304)
    assert harness.state.current.vehicles is before


@pytest.mark.parametrize(
    ("reply", "outcome"),
    [
        (httpx2.Response(503), Outcome.HTTP_ERROR),
        (httpx2.Response(404), Outcome.HTTP_ERROR),
        (httpx2.ConnectTimeout("timed out"), Outcome.NETWORK_ERROR),
        (httpx2.ConnectError("no route to host"), Outcome.NETWORK_ERROR),
        (ok(b"<html>Bad gateway</html>"), Outcome.DECODE_ERROR),
        (ok(feed_bytes(vehicle(), version="1.0")), Outcome.REJECTED),
        (ok(feed_bytes(vehicle(), timestamp=NOW + 3600)), Outcome.REJECTED),
        (ok(feed_bytes(vehicle(), timestamp=NOW)), Outcome.UNCHANGED),
        (ok(feed_bytes(vehicle(), timestamp=NOW - 30)), Outcome.STALE_RESPONSE),
    ],
    ids=["503", "404", "timeout", "unreachable", "html", "old-version", "future", "same", "older"],
)
async def test_a_response_that_cannot_be_used_leaves_the_snapshot_in_place(
    reply: httpx2.Response | Exception, outcome: Outcome
) -> None:
    harness = Harness()
    await harness.poll(ok(feed_bytes(vehicle("KEEP"))))
    before = harness.state.current.vehicles

    record = await harness.poll(reply)

    assert record.outcome is outcome
    assert record.accepted_count is None
    assert harness.state.current.vehicles is before
    assert len(harness.records) == 2


async def test_failures_say_what_went_wrong() -> None:
    harness = Harness()

    timeout = await harness.poll(httpx2.ConnectTimeout("timed out"))
    rejected = await harness.poll(ok(feed_bytes(vehicle(), version="1.0")))

    assert timeout.detail == "ConnectTimeout: timed out"
    assert timeout.http_status is None
    assert rejected.detail == "unsupported_version_1.0"
    assert harness.state.current.vehicles is None


async def test_a_rejected_response_does_not_change_the_conditional_header() -> None:
    harness = Harness()
    await harness.poll(ok(feed_bytes(vehicle()), "Sun, 15 Nov 2026 23:00:00 GMT"))
    await harness.poll(ok(b"not a feed", "Sun, 15 Nov 2026 23:00:30 GMT"))

    await harness.poll(httpx2.Response(304))

    # Otherwise the server would answer 304 for a body we never managed to use.
    assert harness.requests[2].headers["if-modified-since"] == "Sun, 15 Nov 2026 23:00:00 GMT"


async def test_newer_data_replaces_the_snapshot() -> None:
    harness = Harness()
    await harness.poll(ok(feed_bytes(vehicle("OLD"), timestamp=NOW)))
    harness.now = NOW + 35

    record = await harness.poll(
        ok(feed_bytes(vehicle("NEW", timestamp=NOW + 25), timestamp=NOW + 30))
    )

    assert record.outcome is Outcome.OK
    snapshot = harness.state.current.vehicles
    assert snapshot is not None
    assert [v.vehicle_id for v in snapshot.items] == ["NEW"]
    assert snapshot.source_timestamp == NOW + 30


async def test_without_a_static_schedule_nothing_is_fetched() -> None:
    harness = Harness(reference=None)

    record = await harness.collector.poll_once(VP)

    assert record.outcome is Outcome.NO_REFERENCE
    assert harness.requests == []
    assert harness.state.current.vehicles is None
    assert harness.records == [record]


async def test_a_sudden_collapse_in_entity_count_is_flagged_but_still_published() -> None:
    harness = Harness()
    for step in range(5):
        harness.now = NOW + step * 30 + 5
        body = feed_bytes(*(vehicle(f"V{n}") for n in range(10)), timestamp=NOW + step * 30)
        assert (await harness.poll(ok(body))).anomaly is False
    harness.now = NOW + 155

    record = await harness.poll(
        ok(feed_bytes(vehicle("ONLY", timestamp=NOW + 140), timestamp=NOW + 150))
    )

    assert (record.outcome, record.anomaly, record.entity_count) == (Outcome.OK, True, 1)
    snapshot = harness.state.current.vehicles
    assert snapshot is not None and snapshot.anomaly is True
    assert [v.vehicle_id for v in snapshot.items] == ["ONLY"]


async def test_a_lasting_change_stops_being_flagged_once_it_is_the_norm() -> None:
    harness = Harness()
    flags = []
    for step in range(30):
        harness.now = NOW + step * 30 + 5
        count = 10 if step < 5 else 1
        body = feed_bytes(
            *(vehicle(f"V{n}", timestamp=NOW + step * 30 - 5) for n in range(count)),
            timestamp=NOW + step * 30,
        )
        flags.append((await harness.poll(ok(body))).anomaly)

    assert flags[5] is True
    assert flags[-1] is False


async def test_a_failing_fetch_log_does_not_stop_collection() -> None:
    def broken(record: FetchRecord) -> None:
        raise ConnectionError("database is down")

    harness = Harness(record_fetch=broken)

    record = await harness.poll(ok(feed_bytes(vehicle())))

    assert record.outcome is Outcome.OK
    assert harness.state.current.vehicles is not None


async def test_the_polling_loop_survives_an_unexpected_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = Harness()
    calls: list[int] = []

    async def flaky(feed: FeedName) -> Any:
        calls.append(len(calls))
        if len(calls) == 1:
            raise RuntimeError("bug in one cycle")

    monkeypatch.setattr(harness.collector, "poll_once", flaky)
    task = asyncio.create_task(harness.collector.run_feed(VP, interval_s=0.01))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(calls) >= 3


async def test_a_listener_hears_of_each_published_snapshot_only() -> None:
    heard: list[FeedName] = []
    harness = Harness()
    harness.collector._on_publish = heard.append

    await harness.poll(ok(feed_bytes(vehicle())))
    await harness.poll(httpx2.Response(304))
    await harness.poll(httpx2.Response(503))
    await harness.poll(ok(feed_bytes(trip_update(), timestamp=NOW)), FeedName.TRIP_UPDATES)

    assert heard == [FeedName.VEHICLE_POSITIONS, FeedName.TRIP_UPDATES]


async def test_a_failing_listener_does_not_cost_the_collected_data() -> None:
    def broken(feed: FeedName) -> None:
        raise RuntimeError("listener bug")

    harness = Harness()
    harness.collector._on_publish = broken

    record = await harness.poll(ok(feed_bytes(vehicle())))

    assert record.outcome is Outcome.OK
    assert harness.state.current.vehicles is not None
