"""Polls TransLink's real-time feeds and keeps the live state current (architecture §4.1).

One poll of one feed: fetch, decode, judge the response as a whole, validate each
record, swap in the new snapshot, and log what happened. A failure at any step leaves
the previous snapshot in place; it simply ages, and its freshness state degrades.
"""

import asyncio
import dataclasses
import datetime as dt
import enum
import logging
import statistics
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx2
from google.transit import gtfs_realtime_pb2

from brispulse.config import Settings
from brispulse.realtime import decode, normalise
from brispulse.realtime.model import FEED_PATHS, FeedName, FeedSnapshot, FeedStats, LiveState
from brispulse.realtime.reference import Reference
from brispulse.realtime.thresholds import DEFAULT_THRESHOLDS, Thresholds

logger = logging.getLogger(__name__)

# How long to wait before looking again when no schedule has loaded yet.
_SCHEDULE_WAIT_SECONDS = 2.0


class Outcome(enum.StrEnum):
    OK = "ok"
    # The server answered 304: nothing newer than what we already hold.
    NOT_MODIFIED = "not_modified"
    # A full response whose data timestamp equals the one we already hold.
    UNCHANGED = "unchanged"
    # A full response older than the data we already hold.
    STALE_RESPONSE = "stale_response"
    HTTP_ERROR = "http_error"
    NETWORK_ERROR = "network_error"
    DECODE_ERROR = "decode_error"
    REJECTED = "rejected"
    # No static schedule has been imported, so nothing can be validated.
    NO_REFERENCE = "no_reference"


@dataclass(frozen=True, slots=True)
class FetchRecord:
    """One row of the fetch log."""

    feed: FeedName
    fetched_at: dt.datetime
    duration_ms: int
    outcome: Outcome
    http_status: int | None = None
    body_bytes: int | None = None
    source_timestamp: dt.datetime | None = None
    entity_count: int | None = None
    accepted_count: int | None = None
    rejected: Mapping[str, int] | None = None
    anomaly: bool = False
    detail: str | None = None
    static_version_id: int | None = None


class LiveStateHolder:
    """Holds the current ``LiveState``.

    The state object is immutable and is replaced whole, on the event loop thread. A
    reader therefore always sees a complete, consistent picture.
    """

    def __init__(self) -> None:
        self.current = LiveState()
        # The latest attempt per feed, successful or not, for the status endpoint.
        self.last_attempts: dict[FeedName, FetchRecord] = {}

    def publish(self, snapshot: FeedSnapshot[Any]) -> None:
        field_name = {
            FeedName.VEHICLE_POSITIONS: "vehicles",
            FeedName.TRIP_UPDATES: "trip_updates",
            FeedName.ALERTS: "alerts",
        }[snapshot.feed]
        self.current = dataclasses.replace(self.current, **{field_name: snapshot})

    def snapshot(self, feed: FeedName) -> FeedSnapshot[Any] | None:
        state = self.current
        return {
            FeedName.VEHICLE_POSITIONS: state.vehicles,
            FeedName.TRIP_UPDATES: state.trip_updates,
            FeedName.ALERTS: state.alerts,
        }[feed]


@dataclass(slots=True)
class _FeedMemory:
    """What the collector remembers about a feed between polls."""

    # Sent back as If-Modified-Since. TransLink answers it with 304; it ignores ETags
    # (verified live on 2026-11-16).
    last_modified: str | None = None
    recent_counts: deque[int] = field(default_factory=deque)


@dataclass(frozen=True, slots=True)
class _Processed:
    outcome: Outcome
    snapshot: FeedSnapshot[Any] | None = None
    detail: str | None = None
    source_timestamp: int | None = None
    entity_count: int | None = None


def _normalise(
    feed: FeedName,
    message: gtfs_realtime_pb2.FeedMessage,
    reference: Reference,
    thresholds: Thresholds,
) -> tuple[tuple[Any, ...], FeedStats]:
    if feed is FeedName.VEHICLE_POSITIONS:
        return normalise.normalise_vehicles(message, reference, thresholds)
    if feed is FeedName.TRIP_UPDATES:
        return normalise.normalise_trip_updates(message, reference, thresholds)
    return normalise.normalise_alerts(message, reference)


def process_body(
    feed: FeedName,
    body: bytes,
    *,
    reference: Reference,
    now: float,
    previous_timestamp: int | None,
    thresholds: Thresholds,
) -> _Processed:
    """Decode and validate one response body. Pure CPU work; runs off the event loop."""
    try:
        message = decode.decode_feed(body)
    except decode.FeedDecodeError as exc:
        return _Processed(Outcome.DECODE_ERROR, detail=str(exc)[:200])

    source_timestamp = int(message.header.timestamp) or None
    entity_count = len(message.entity)
    check = decode.check_header(
        message, now=now, previous_timestamp=previous_timestamp, thresholds=thresholds
    )
    if check.verdict is not decode.HeaderVerdict.OK:
        return _Processed(
            Outcome(check.verdict.value),
            detail=check.reason,
            source_timestamp=source_timestamp,
            entity_count=entity_count,
        )

    items, stats = _normalise(feed, message, reference, thresholds)
    snapshot = FeedSnapshot(
        feed=feed,
        source_timestamp=int(message.header.timestamp),
        fetched_at=now,
        items=items,
        stats=stats,
        static_version_id=reference.version_id,
    )
    return _Processed(
        Outcome.OK,
        snapshot=snapshot,
        source_timestamp=source_timestamp,
        entity_count=entity_count,
    )


def _utc(epoch: float) -> dt.datetime:
    return dt.datetime.fromtimestamp(epoch, dt.UTC)


class Collector:
    def __init__(
        self,
        settings: Settings,
        client: httpx2.AsyncClient,
        state: LiveStateHolder,
        get_reference: Callable[[], Reference | None],
        record_fetch: Callable[[FetchRecord], None],
        *,
        on_publish: Callable[[FeedName], None] | None = None,
        thresholds: Thresholds = DEFAULT_THRESHOLDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._settings = settings
        self._client = client
        # Told about every newly published snapshot (the history recorder listens).
        self._on_publish = on_publish
        self._state = state
        self._get_reference = get_reference
        self._record_fetch = record_fetch
        self._thresholds = thresholds
        self._clock = clock
        self._memory = {feed: _FeedMemory() for feed in FeedName}

    def _url(self, feed: FeedName) -> str:
        return (
            self._settings.translink_base_url.rstrip("/")
            + self._settings.realtime_path
            + "/"
            + FEED_PATHS[feed]
        )

    def _is_anomalous(self, memory: _FeedMemory, entity_count: int) -> bool:
        """True when this fetch has far fewer entities than recent ones.

        The count is added to the history either way, so a real, lasting change stops
        being flagged once the window has caught up. The flag marks the sudden drop.
        """
        counts = memory.recent_counts
        anomalous = (
            len(counts) >= self._thresholds.anomaly_min_samples
            and entity_count < statistics.median(counts) * self._thresholds.anomaly_fraction
        )
        counts.append(entity_count)
        while len(counts) > self._thresholds.anomaly_window:
            counts.popleft()
        return anomalous

    async def poll_once(self, feed: FeedName) -> FetchRecord:
        """Fetch and process one feed once. Never raises; the outcome says what happened."""
        started = self._clock()
        timer = time.perf_counter()
        record = await self._poll(feed, started)
        record = dataclasses.replace(record, duration_ms=int((time.perf_counter() - timer) * 1000))
        self._state.last_attempts[feed] = record
        if record.outcome is Outcome.NO_REFERENCE:
            # Nothing was attempted, so there is nothing to log as a fetch.
            return record
        if record.outcome not in (Outcome.OK, Outcome.NOT_MODIFIED, Outcome.UNCHANGED):
            logger.warning("feed %s: %s %s", feed.value, record.outcome.value, record.detail or "")
        try:
            # The log write is blocking database I/O, so it stays off the event loop.
            await asyncio.to_thread(self._record_fetch, record)
        except Exception:
            # Losing a log row must not stop collection (architecture §7, database down).
            logger.exception("could not write the fetch log for %s", feed.value)
        return record

    async def _poll(self, feed: FeedName, started: float) -> FetchRecord:
        base = FetchRecord(feed=feed, fetched_at=_utc(started), duration_ms=0, outcome=Outcome.OK)
        reference = self._get_reference()
        if reference is None:
            return dataclasses.replace(base, outcome=Outcome.NO_REFERENCE)
        base = dataclasses.replace(base, static_version_id=reference.version_id)

        memory = self._memory[feed]
        headers = {"If-Modified-Since": memory.last_modified} if memory.last_modified else {}
        try:
            response = await self._client.get(self._url(feed), headers=headers)
        except httpx2.HTTPError as exc:
            detail = f"{type(exc).__name__}: {exc}"[:200]
            return dataclasses.replace(base, outcome=Outcome.NETWORK_ERROR, detail=detail)

        base = dataclasses.replace(base, http_status=response.status_code)
        if response.status_code == 304:
            return dataclasses.replace(base, outcome=Outcome.NOT_MODIFIED)
        if response.status_code != 200:
            return dataclasses.replace(base, outcome=Outcome.HTTP_ERROR)

        body = response.content
        current = self._state.snapshot(feed)
        processed = await asyncio.to_thread(
            process_body,
            feed,
            body,
            reference=reference,
            now=started,
            previous_timestamp=current.source_timestamp if current else None,
            thresholds=self._thresholds,
        )
        record = dataclasses.replace(
            base,
            outcome=processed.outcome,
            body_bytes=len(body),
            detail=processed.detail,
            entity_count=processed.entity_count,
            source_timestamp=(
                _utc(processed.source_timestamp) if processed.source_timestamp else None
            ),
        )
        if processed.snapshot is None:
            return record

        snapshot = processed.snapshot
        anomaly = self._is_anomalous(memory, snapshot.stats.entity_count)
        if anomaly:
            logger.warning(
                "feed %s: entity count fell to %d", feed.value, snapshot.stats.entity_count
            )
            snapshot = dataclasses.replace(snapshot, anomaly=True)
        stats = snapshot.stats
        if (
            feed is not FeedName.ALERTS
            and stats.accepted
            and stats.unmatched / stats.accepted > self._thresholds.static_mismatch_fraction
        ):
            logger.warning(
                "feed %s: %d of %d records do not match static version %s",
                feed.value,
                stats.unmatched,
                stats.accepted,
                reference.version_id,
            )
        # Only a response that was accepted may be used for the next conditional request.
        memory.last_modified = response.headers.get("last-modified")
        self._state.publish(snapshot)
        if self._on_publish is not None:
            try:
                self._on_publish(feed)
            except Exception:
                # A listener's failure must not cost the data that was just collected.
                logger.exception("listener failed after publishing %s", feed.value)
        return dataclasses.replace(
            record,
            accepted_count=snapshot.stats.accepted,
            rejected=dict(snapshot.stats.rejected),
            anomaly=anomaly,
        )

    async def run_feed(self, feed: FeedName, interval_s: float) -> None:
        """Poll one feed forever, once per interval, measured start to start."""
        while True:
            cycle_started = time.monotonic()
            waiting_for_schedule = False
            try:
                record = await self.poll_once(feed)
                waiting_for_schedule = record.outcome is Outcome.NO_REFERENCE
            except asyncio.CancelledError:
                raise
            except Exception:
                # A bug in one cycle must not end collection for good.
                logger.exception("unexpected error while polling %s", feed.value)
            if waiting_for_schedule:
                # Nothing was fetched. Look again soon, so live data appears as soon as
                # the schedule has loaded rather than a whole interval later.
                await asyncio.sleep(min(interval_s, _SCHEDULE_WAIT_SECONDS))
                continue
            elapsed = time.monotonic() - cycle_started
            await asyncio.sleep(max(0.0, interval_s - elapsed))

    async def run(self) -> None:
        intervals = {
            FeedName.VEHICLE_POSITIONS: self._settings.poll_vehicle_positions_seconds,
            FeedName.TRIP_UPDATES: self._settings.poll_trip_updates_seconds,
            FeedName.ALERTS: self._settings.poll_alerts_seconds,
        }
        async with asyncio.TaskGroup() as group:
            for feed, interval in intervals.items():
                group.create_task(self.run_feed(feed, interval), name=f"poll-{feed.value}")
