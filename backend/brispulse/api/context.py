"""Everything one request needs to answer from the live state, captured at one instant."""

import datetime as dt
from collections.abc import Mapping
from functools import cached_property
from typing import Any
from zoneinfo import ZoneInfo

from brispulse.api.schemas import FeedMeta, StaticMeta
from brispulse.config import Settings
from brispulse.realtime.collector import FetchRecord
from brispulse.realtime.freshness import Freshness, data_is_usable, feed_freshness
from brispulse.realtime.model import FeedName, FeedSnapshot, LiveState
from brispulse.realtime.populations import RunningTrip, running_trips
from brispulse.realtime.reference import Reference
from brispulse.realtime.thresholds import DEFAULT_THRESHOLDS, FRESHNESS_LIMITS, Thresholds


class Context:
    def __init__(
        self,
        *,
        state: LiveState,
        last_attempts: Mapping[FeedName, FetchRecord],
        reference: Reference | None,
        now: float,
        settings: Settings,
        thresholds: Thresholds = DEFAULT_THRESHOLDS,
    ) -> None:
        # ``state`` is immutable, so the whole request sees one consistent picture even
        # if the collector publishes new data while the response is being built.
        self.state = state
        self.last_attempts = last_attempts
        self.reference = reference
        self.now = now
        self.settings = settings
        self.thresholds = thresholds
        self.timezone = ZoneInfo(settings.service_timezone)

    def at(self, epoch: float) -> dt.datetime:
        """Epoch seconds as a datetime carrying the service's local offset."""
        return dt.datetime.fromtimestamp(epoch, self.timezone)

    def local(self, epoch: float | None) -> dt.datetime | None:
        """Like ``at``, for a value that may be missing."""
        return self.at(epoch) if epoch is not None else None

    def snapshot(self, feed: FeedName) -> FeedSnapshot[Any] | None:
        return {
            FeedName.VEHICLE_POSITIONS: self.state.vehicles,
            FeedName.TRIP_UPDATES: self.state.trip_updates,
            FeedName.ALERTS: self.state.alerts,
        }[feed]

    def freshness(self, feed: FeedName) -> Freshness:
        snapshot = self.snapshot(feed)
        return feed_freshness(feed, snapshot.source_timestamp if snapshot else None, self.now)

    def usable(self, feed: FeedName) -> FeedSnapshot[Any] | None:
        """The feed's data, or None when it must be withheld as unavailable."""
        return self.snapshot(feed) if data_is_usable(self.freshness(feed)) else None

    def feed_meta(self, feed: FeedName) -> FeedMeta:
        snapshot = self.snapshot(feed)
        if snapshot is None:
            return FeedMeta(
                state=Freshness.UNAVAILABLE,
                source_timestamp=None,
                fetched_at=None,
                age_seconds=None,
                anomaly=False,
            )
        return FeedMeta(
            state=self.freshness(feed),
            source_timestamp=self.local(snapshot.source_timestamp),
            fetched_at=self.local(snapshot.fetched_at),
            age_seconds=max(0, int(self.now - snapshot.source_timestamp)),
            anomaly=snapshot.anomaly,
        )

    def static_meta(self) -> StaticMeta | None:
        reference = self.reference
        if reference is None:
            return None
        return StaticMeta(
            version_id=reference.version_id,
            published_at=reference.published_at,
            feed_start_date=reference.feed_start_date,
            feed_end_date=reference.feed_end_date,
        )

    def feed_notes(self, feed: FeedName) -> list[str]:
        """Plain-language caveats about a feed that is not live."""
        snapshot = self.snapshot(feed)
        state = self.freshness(feed)
        if snapshot is None:
            return [f"{feed.value}: no data has been retrieved yet, so its values are null."]
        age = max(0, int(self.now - snapshot.source_timestamp))
        notes: list[str] = []
        if state is Freshness.UNAVAILABLE:
            limit = FRESHNESS_LIMITS[feed].stale_s
            notes.append(
                f"{feed.value}: the latest data is {age} s old, beyond the {limit} s limit, "
                "so its values are withheld as null."
            )
        elif state is not Freshness.LIVE:
            notes.append(f"{feed.value}: data is {state.value} ({age} s old).")
        if snapshot.anomaly:
            notes.append(f"{feed.value}: far fewer records than usual in the latest data.")
        return notes

    @cached_property
    def running(self) -> list[RunningTrip] | None:
        """Running trips, or None when either feed they depend on is unavailable."""
        vehicles = self.usable(FeedName.VEHICLE_POSITIONS)
        trips = self.usable(FeedName.TRIP_UPDATES)
        if vehicles is None or trips is None:
            return None
        return running_trips(vehicles, trips, self.timezone)
