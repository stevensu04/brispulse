"""Summaries of predicted delay (architecture §6.2).

Only percentiles and counts: no averages, because a handful of extreme predictions
would dominate them. Implausible delays are left out and counted, never silently.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass

from brispulse.realtime.populations import RunningTrip
from brispulse.realtime.thresholds import Thresholds


@dataclass(frozen=True, slots=True)
class DelaySummary:
    # Trips whose delay went into the figures below.
    sample_size: int
    # Running trips left out because their delay was beyond the plausible range.
    excluded_implausible: int
    # Running trips for which the feed gave no delay at all.
    without_delay: int
    # None when the sample is too small to summarise.
    median_s: int | None
    p90_s: int | None
    early: int
    within_band: int
    late: int


def nearest_rank(sorted_values: list[int], fraction: float) -> int:
    """The nearest-rank percentile: always one of the observed values."""
    rank = max(1, math.ceil(fraction * len(sorted_values)))
    return sorted_values[rank - 1]


def summarise_delays(trips: Iterable[RunningTrip], thresholds: Thresholds) -> DelaySummary:
    delays: list[int] = []
    excluded = without = 0
    for running in trips:
        delay = running.trip.next_stop_delay_s
        if delay is None:
            without += 1
        elif running.trip.delay_implausible:
            excluded += 1
        else:
            delays.append(delay)
    delays.sort()
    enough = len(delays) >= thresholds.min_sample
    return DelaySummary(
        sample_size=len(delays),
        excluded_implausible=excluded,
        without_delay=without,
        median_s=nearest_rank(delays, 0.5) if enough else None,
        p90_s=nearest_rank(delays, 0.9) if enough else None,
        early=sum(1 for d in delays if d < -thresholds.delay_early_s),
        within_band=sum(
            1 for d in delays if -thresholds.delay_early_s <= d <= thresholds.delay_late_s
        ),
        late=sum(1 for d in delays if d > thresholds.delay_late_s),
    )
