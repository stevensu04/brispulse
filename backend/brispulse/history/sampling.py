"""The five-minute network sample (architecture §4.3). Pure: no clock, no database.

A sample is taken only from data fresh enough to trust. A feed that is stale or
unavailable leaves its metrics empty for that sample, so a gap in the data shows up as
a gap in history rather than as a run of repeated or zero values.
"""

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from brispulse.delay_stats import summarise_delays
from brispulse.realtime.freshness import Freshness, feed_freshness
from brispulse.realtime.model import PLANNED_WORKS_CAUSES, FeedName, LiveState
from brispulse.realtime.populations import RunningTrip, running_trips
from brispulse.realtime.thresholds import Thresholds

ALL = "all"

# Only these states are recorded as history. "Stale" data is still shown to users with
# a warning, but it is too old to stand for the moment the sample is labelled with.
_RECORDABLE = frozenset({Freshness.LIVE, Freshness.DELAYED})


@dataclass(frozen=True, slots=True)
class NetworkSampleRow:
    sampled_at: dt.datetime
    mode: str
    static_version_id: int | None
    vehicle_positions_state: str
    trip_updates_state: str
    alerts_state: str
    vehicles_fresh: int | None = None
    vehicles_last_seen: int | None = None
    trips_running: int | None = None
    trips_scheduled: int | None = None
    trips_with_update: int | None = None
    trips_with_vehicle: int | None = None
    delay_sample_size: int | None = None
    delay_median_s: int | None = None
    delay_p90_s: int | None = None
    delay_early: int | None = None
    delay_within_band: int | None = None
    delay_late: int | None = None
    delay_excluded_implausible: int | None = None
    alerts_active: int | None = None
    alerts_active_planned_works: int | None = None


def recordable_running_trips(
    state: LiveState, now: float, timezone: ZoneInfo
) -> list[RunningTrip] | None:
    """Running trips, or None when either feed is too old to record as history."""
    vehicles, trips = state.vehicles, state.trip_updates
    if vehicles is None or trips is None:
        return None
    fresh_enough = (
        feed_freshness(FeedName.VEHICLE_POSITIONS, vehicles.source_timestamp, now) in _RECORDABLE
        and feed_freshness(FeedName.TRIP_UPDATES, trips.source_timestamp, now) in _RECORDABLE
    )
    return running_trips(vehicles, trips, timezone) if fresh_enough else None


def build_network_samples(
    state: LiveState,
    scheduled: Mapping[str, str] | None,
    *,
    sampled_at: dt.datetime,
    now: float,
    timezone: ZoneInfo,
    thresholds: Thresholds,
    static_version_id: int | None,
) -> list[NetworkSampleRow]:
    """One row for the whole network and one per mode present.

    ``scheduled`` maps each trip the schedule says is in progress to its mode, or is
    None when that could not be determined (coverage is then left empty).
    """

    def state_of(feed: FeedName, timestamp: int | None) -> Freshness:
        return feed_freshness(feed, timestamp, now)

    vehicles, trips, alerts = state.vehicles, state.trip_updates, state.alerts
    vp_state = state_of(FeedName.VEHICLE_POSITIONS, vehicles.source_timestamp if vehicles else None)
    tu_state = state_of(FeedName.TRIP_UPDATES, trips.source_timestamp if trips else None)
    alerts_state = state_of(FeedName.ALERTS, alerts.source_timestamp if alerts else None)
    usable_vehicles = vehicles if vehicles is not None and vp_state in _RECORDABLE else None
    usable_trips = trips if trips is not None and tu_state in _RECORDABLE else None
    usable_alerts = alerts if alerts is not None and alerts_state in _RECORDABLE else None
    running = recordable_running_trips(state, now, timezone)

    modes: set[str] = set()
    if usable_vehicles is not None:
        modes.update(v.mode for v in usable_vehicles.items if v.mode)
    if scheduled is not None:
        modes.update(scheduled.values())

    fresh_trip_ids = (
        {v.trip_id for v in usable_vehicles.items if v.fresh and v.trip_id}
        if usable_vehicles is not None
        else None
    )
    updated_trip_ids = {t.trip_id for t in usable_trips.items} if usable_trips is not None else None

    rows: list[NetworkSampleRow] = []
    for mode in [ALL, *sorted(modes)]:

        def included(candidate: str | None, mode: str = mode) -> bool:
            return mode == ALL or candidate == mode

        row: dict[str, int | None] = {}
        if usable_vehicles is not None:
            relevant = [v for v in usable_vehicles.items if included(v.mode)]
            row["vehicles_fresh"] = sum(1 for v in relevant if v.fresh)
            row["vehicles_last_seen"] = sum(1 for v in relevant if not v.fresh)
        if running is not None:
            mine = [r for r in running if included(r.trip.mode)]
            summary = summarise_delays(mine, thresholds)
            row.update(
                trips_running=len(mine),
                delay_sample_size=summary.sample_size,
                delay_median_s=summary.median_s,
                delay_p90_s=summary.p90_s,
                delay_early=summary.early,
                delay_within_band=summary.within_band,
                delay_late=summary.late,
                delay_excluded_implausible=summary.excluded_implausible,
            )
        if scheduled is not None:
            due = {trip_id for trip_id, trip_mode in scheduled.items() if included(trip_mode)}
            row["trips_scheduled"] = len(due)
            if updated_trip_ids is not None:
                row["trips_with_update"] = len(due & updated_trip_ids)
            if fresh_trip_ids is not None:
                row["trips_with_vehicle"] = len(due & fresh_trip_ids)
        if mode == ALL and usable_alerts is not None:
            active = [a for a in usable_alerts.items if a.is_active(now)]
            row["alerts_active"] = len(active)
            row["alerts_active_planned_works"] = sum(
                1 for a in active if a.cause in PLANNED_WORKS_CAUSES
            )
        rows.append(
            NetworkSampleRow(
                sampled_at=sampled_at,
                mode=mode,
                static_version_id=static_version_id,
                vehicle_positions_state=vp_state.value,
                trip_updates_state=tu_state.value,
                alerts_state=alerts_state.value,
                **row,
            )
        )
    return rows
