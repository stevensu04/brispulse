"""Every limit used to judge real-time data, in one place.

Sources are stated per value. "Starting value" means a judgement call approved as such
(architecture §13, A3) and due for review after a week of collected data.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from brispulse.realtime.model import FeedName


@dataclass(frozen=True, slots=True)
class Thresholds:
    # GTFS Realtime best practices: vehicle positions should be no older than 90 s.
    vehicle_fresh_s: int = 90
    # Older than this, a vehicle is not shown at all. Starting value.
    vehicle_drop_s: int = 900
    # A timestamp this far ahead of the feed's own clock is treated as wrong. Starting value.
    future_tolerance_s: int = 60
    # Delays beyond this are shown but excluded from statistics. Starting value; about
    # 0.7 % of running trips exceeded half of it in the M1 snapshots.
    delay_plausible_s: int = 3600

    # South East Queensland bounding box, wider than the range observed on 2026-11-16
    # (lat -28.174..-26.343, lon 152.334..153.543). Starting value.
    lat_min: float = -28.5
    lat_max: float = -25.9
    lon_min: float = 152.0
    lon_max: float = 153.7

    # A fetch with fewer entities than this fraction of the recent median is flagged.
    # Starting values.
    anomaly_fraction: float = 0.2
    anomaly_window: int = 20
    anomaly_min_samples: int = 5

    # Above this share of unmatched records, the static schedule in use probably does
    # not belong to the feed (for example just after TransLink republishes it).
    # Starting value.
    static_mismatch_fraction: float = 0.02


DEFAULT_THRESHOLDS = Thresholds()


@dataclass(frozen=True, slots=True)
class FreshnessLimits:
    """Upper age bounds, in seconds, for the live, delayed and stale states."""

    live_s: int
    delayed_s: int
    stale_s: int


# The "live" limits follow the GTFS Realtime best practices (90 s for vehicle positions
# and trip updates, 10 minutes for alerts). The other limits are starting values.
FRESHNESS_LIMITS: Mapping[FeedName, FreshnessLimits] = {
    FeedName.VEHICLE_POSITIONS: FreshnessLimits(live_s=90, delayed_s=300, stale_s=900),
    FeedName.TRIP_UPDATES: FreshnessLimits(live_s=90, delayed_s=300, stale_s=900),
    FeedName.ALERTS: FreshnessLimits(live_s=600, delayed_s=1800, stale_s=7200),
}
