"""Response shapes. FastAPI publishes these as the OpenAPI contract.

Convention used throughout: a value that cannot be given is ``null``, never ``0`` or an
empty list. ``meta.notes`` says why.
"""

import datetime as dt

from pydantic import BaseModel

from brispulse.realtime.freshness import Freshness
from brispulse.realtime.model import FeedName


class FeedMeta(BaseModel):
    state: Freshness
    # When TransLink produced the data.
    source_timestamp: dt.datetime | None
    # When BrisPulse retrieved it.
    fetched_at: dt.datetime | None
    age_seconds: int | None
    # The feed suddenly held far fewer records than usual.
    anomaly: bool


class StaticMeta(BaseModel):
    version_id: int
    published_at: dt.datetime | None
    feed_start_date: dt.date | None
    feed_end_date: dt.date | None


class Meta(BaseModel):
    generated_at: dt.datetime
    # Only the feeds this response was built from.
    feeds: dict[FeedName, FeedMeta]
    static_version: StaticMeta | None
    notes: list[str]


class Envelope[T](BaseModel):
    data: T | None
    meta: Meta


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


# --- status -----------------------------------------------------------------------


class FeedStatus(FeedMeta):
    entity_count: int | None
    accepted: int | None
    rejected: dict[str, int] | None
    unmatched: int | None
    dropped_stale: int | None
    last_attempt_at: dt.datetime | None
    last_attempt_outcome: str | None


class StaticStatus(StaticMeta):
    routes: int
    stops: int
    trips: int


class StatusData(BaseModel):
    feeds: dict[FeedName, FeedStatus]
    static: StaticStatus | None
    poll_interval_seconds: dict[FeedName, float]
    # False in a live-only deployment: nothing is stored, so there are no trends and
    # no real-time coverage.
    history_enabled: bool


# --- shared references ------------------------------------------------------------


class RouteRef(BaseModel):
    route_id: str
    short_name: str | None
    long_name: str | None
    mode: str | None


class StopRef(BaseModel):
    stop_id: str
    name: str | None


# --- overview ---------------------------------------------------------------------


class DelaySummaryOut(BaseModel):
    """Predicted delay at the next stop, across running trips. Not on-time performance."""

    sample_size: int
    excluded_implausible: int
    without_delay: int
    median_s: int | None
    p90_s: int | None
    early: int
    within_band: int
    late: int


class VehicleOverview(BaseModel):
    fresh: int
    last_seen: int
    fresh_by_mode: dict[str, int]


class TripOverview(BaseModel):
    running: int
    running_by_mode: dict[str, int]
    canceled: int
    delay: DelaySummaryOut
    delay_by_mode: dict[str, DelaySummaryOut]


class AlertOverview(BaseModel):
    in_feed: int
    active: int
    # Active alerts whose stated cause is construction or maintenance.
    active_planned_works: int
    # Every other active alert. Not a count of incidents: it includes timetable
    # changes and general notices, which TransLink files under other causes.
    active_other: int


class CoverageCounts(BaseModel):
    """Of the trips the schedule says are in progress, how many have live data."""

    trips_scheduled: int
    # None when that feed was not usable at the time of the sample.
    trips_with_update: int | None
    trips_with_vehicle: int | None


class CoverageOut(CoverageCounts):
    # Coverage is computed on the clock, every few minutes, not per request.
    sampled_at: dt.datetime
    by_mode: dict[str, CoverageCounts]


class OverviewData(BaseModel):
    vehicles: VehicleOverview | None
    trips: TripOverview | None
    alerts: AlertOverview | None
    coverage: CoverageOut | None


# --- vehicles ---------------------------------------------------------------------


class VehicleOut(BaseModel):
    vehicle_id: str
    label: str | None
    lat: float
    lon: float
    mode: str | None
    route_id: str | None
    route_short_name: str | None
    trip_id: str | None
    headsign: str | None
    status: str | None
    stop: StopRef | None
    reported_at: dt.datetime
    # False: a "last seen" position, more than the freshness limit old.
    fresh: bool
    # False: trip or route is not in the static schedule; excluded from metrics.
    matched: bool
    # Predicted delay at the next stop, only when the vehicle's trip is running.
    predicted_delay_s: int | None


# --- alerts -----------------------------------------------------------------------


class ActivePeriodOut(BaseModel):
    start: dt.datetime | None
    end: dt.datetime | None


class AlertOut(BaseModel):
    alert_id: str
    cause: str
    effect: str
    # The stated cause is construction or maintenance. False does not mean unplanned.
    planned_works: bool
    active: bool
    header: str | None
    description: str | None
    url: str | None
    active_periods: list[ActivePeriodOut]
    routes: list[RouteRef]
    stops: list[StopRef]


# --- routes -----------------------------------------------------------------------


class RouteSummary(RouteRef):
    color: str | None
    text_color: str | None
    vehicles_fresh: int | None
    trips_running: int | None
    alerts_active: int | None


class TripBrief(BaseModel):
    trip_id: str
    headsign: str | None
    relationship: str
    scheduled_start: dt.datetime | None
    vehicle_id: str | None
    predicted_delay_s: int | None
    delay_implausible: bool
    next_stop: StopRef | None


class RouteDetail(BaseModel):
    route: RouteSummary
    vehicles: list[VehicleOut] | None
    running_trips: list[TripBrief] | None
    alerts: list[AlertOut] | None


# --- trips ------------------------------------------------------------------------


class StopPredictionOut(BaseModel):
    stop: StopRef
    stop_sequence: int | None
    arrival_time: dt.datetime | None
    arrival_delay_s: int | None
    departure_time: dt.datetime | None
    departure_delay_s: int | None


class TripRealtime(BaseModel):
    relationship: str
    scheduled_start: dt.datetime | None
    # None when vehicle positions are unavailable, so it cannot be determined.
    running: bool | None
    vehicle_id: str | None
    updated_at: dt.datetime | None
    predicted_delay_s: int | None
    delay_implausible: bool
    stops: list[StopPredictionOut]


class TripDetail(BaseModel):
    trip_id: str
    in_schedule: bool
    route: RouteRef | None
    headsign: str | None
    realtime: TripRealtime | None


# --- analytics (M4, live-only) ----------------------------------------------------


class RouteLateness(BaseModel):
    """One route's running trips right now, by predicted delay at the next stop."""

    route: RouteRef
    running: int
    late: int
    early: int
    # The largest plausible predicted delay among the route's running trips.
    worst_delay_s: int


class RouteAlertCount(BaseModel):
    route: RouteRef
    active_alerts: int


class DelayAnalytics(BaseModel):
    # Running trips whose delay counted (plausible, present).
    trips_counted: int
    routes_with_running_trips: int
    routes_with_late_trips: int
    # The routes with the most late trips right now, most first. Counts, not
    # percentages: most routes have only a few trips running at any moment.
    late_routes: list[RouteLateness]


class AlertAnalytics(BaseModel):
    active: int
    by_effect: dict[str, int]
    by_cause: dict[str, int]
    # The routes named by the most active alerts, most first.
    routes_most_affected: list[RouteAlertCount]


class AnalyticsNow(BaseModel):
    """Descriptive figures for the present moment. This deployment keeps no history."""

    delays: DelayAnalytics | None
    alerts: AlertAnalytics | None


# --- metric definitions -----------------------------------------------------------


class MetricDefinition(BaseModel):
    name: str
    definition: str
    source: str
    limitations: str


class MetricsData(BaseModel):
    metrics: list[MetricDefinition]
    thresholds: dict[str, float]
    freshness_limits_seconds: dict[FeedName, dict[str, int]]
    attribution: str
    disclaimer: str
