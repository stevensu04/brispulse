"""Normalised real-time records.

The collector turns Protobuf messages into these immutable objects once. Everything
downstream (API, metrics) reads them and never touches Protobuf.
"""

import datetime as dt
import enum
from collections.abc import Mapping
from dataclasses import dataclass
from typing import NamedTuple


class FeedName(enum.StrEnum):
    VEHICLE_POSITIONS = "vehicle_positions"
    TRIP_UPDATES = "trip_updates"
    ALERTS = "alerts"


# Path segment under ``/api/realtime/SEQ/`` for each feed (verified live, 2026-11-16).
FEED_PATHS: Mapping[FeedName, str] = {
    FeedName.VEHICLE_POSITIONS: "VehiclePositions",
    FeedName.TRIP_UPDATES: "TripUpdates",
    FeedName.ALERTS: "Alerts",
}


@dataclass(frozen=True, slots=True)
class Vehicle:
    vehicle_id: str
    label: str | None
    trip_id: str | None
    route_id: str | None
    # None when the route does not resolve in the active static version.
    mode: str | None
    lat: float
    lon: float
    status: str | None
    stop_id: str | None
    stop_sequence: int | None
    # When the vehicle reported this position (epoch seconds).
    timestamp: int
    # Seconds between this report and the feed's own timestamp.
    age_s: int
    # Within the freshness limit at the time the feed was produced.
    fresh: bool
    # Trip and route both resolve in the active static version.
    matched: bool


class StopPrediction(NamedTuple):
    """TransLink's prediction for one upcoming stop of a trip."""

    stop_id: str
    stop_sequence: int | None
    arrival_time: int | None
    arrival_delay_s: int | None
    departure_time: int | None
    departure_delay_s: int | None


@dataclass(frozen=True, slots=True)
class TripState:
    trip_id: str
    route_id: str | None
    mode: str | None
    # GTFS service date and start time (seconds after that day's midnight, may exceed 86,400).
    start_date: dt.date | None
    start_time_s: int | None
    # Lower-cased GTFS-RT schedule relationship: scheduled, canceled, replacement, ...
    relationship: str
    vehicle_id: str | None
    timestamp: int | None
    # Predicted delay at the first listed stop, which is the current or next stop.
    # Positive is late. This is a prediction, never an observed arrival.
    next_stop_delay_s: int | None
    # The delay is beyond the plausible range: shown, but kept out of statistics.
    delay_implausible: bool
    predictions: tuple[StopPrediction, ...]
    matched: bool

    @property
    def canceled(self) -> bool:
        return self.relationship == "canceled"


class ActivePeriod(NamedTuple):
    """Epoch seconds. A missing bound means open-ended on that side."""

    start: int | None
    end: int | None


@dataclass(frozen=True, slots=True)
class Alert:
    alert_id: str
    cause: str
    effect: str
    header: str | None
    description: str | None
    url: str | None
    active_periods: tuple[ActivePeriod, ...]
    route_ids: tuple[str, ...]
    stop_ids: tuple[str, ...]
    # Referenced IDs that do not resolve in the active static version.
    unresolved_route_ids: tuple[str, ...]
    unresolved_stop_ids: tuple[str, ...]

    def is_active(self, now: float) -> bool:
        """True when ``now`` falls inside an active period.

        An alert without any period is active for as long as it is in the feed, as the
        GTFS-Realtime specification defines.
        """
        if not self.active_periods:
            return True
        return any(
            (period.start is None or period.start <= now)
            and (period.end is None or now <= period.end)
            for period in self.active_periods
        )


@dataclass(frozen=True, slots=True)
class FeedStats:
    """What happened to the entities of one fetched feed."""

    entity_count: int
    accepted: int
    # Reason -> number of entities rejected for it.
    rejected: Mapping[str, int]
    # Accepted, but trip or route does not resolve in the static schedule.
    unmatched: int = 0
    # Vehicles too old to show at all.
    dropped_stale: int = 0
    implausible_delays: int = 0
    canceled: int = 0


@dataclass(frozen=True, slots=True)
class FeedSnapshot[T]:
    """One feed as last successfully fetched. Immutable: a new fetch replaces it whole."""

    feed: FeedName
    # The feed header's timestamp: when TransLink produced this data (epoch seconds).
    source_timestamp: int
    # When BrisPulse retrieved it (epoch seconds).
    fetched_at: float
    items: tuple[T, ...]
    stats: FeedStats
    static_version_id: int
    # Entity count collapsed relative to recent fetches (architecture §4.1).
    anomaly: bool = False


@dataclass(frozen=True, slots=True)
class LiveState:
    """The current picture of the network. ``None`` means never fetched successfully."""

    vehicles: FeedSnapshot[Vehicle] | None = None
    trip_updates: FeedSnapshot[TripState] | None = None
    alerts: FeedSnapshot[Alert] | None = None
