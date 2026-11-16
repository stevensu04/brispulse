"""Builds each endpoint's data from the live state. No HTTP in here.

Every function returns a ``View``: the data, the feeds it was built from, and any notes.
A function that needs a feed which is unavailable returns ``None`` for the affected
values, never zero and never an empty list (architecture §8).
"""

import datetime as dt
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from brispulse.api.context import Context
from brispulse.api.schemas import (
    ActivePeriodOut,
    AlertOut,
    AlertOverview,
    DelaySummaryOut,
    FeedStatus,
    MetricDefinition,
    MetricsData,
    OverviewData,
    RouteDetail,
    RouteRef,
    RouteSummary,
    StaticStatus,
    StatusData,
    StopPredictionOut,
    StopRef,
    TripBrief,
    TripDetail,
    TripOverview,
    TripRealtime,
    VehicleOut,
    VehicleOverview,
)
from brispulse.delay_stats import DelaySummary, summarise_delays
from brispulse.realtime.model import Alert, FeedName, TripState, Vehicle
from brispulse.realtime.populations import RunningTrip, service_start_epoch
from brispulse.realtime.reference import Reference
from brispulse.realtime.thresholds import FRESHNESS_LIMITS

VP, TU, ALERTS = FeedName.VEHICLE_POSITIONS, FeedName.TRIP_UPDATES, FeedName.ALERTS

# Alerts with these causes are labelled planned works. The label is deliberately narrow:
# in the live feed on 2026-11-16, alerts filed under "other_cause" included planned
# timetable changes and general notices, so the remaining alerts are not all incidents.
PLANNED_WORKS_CAUSES = frozenset({"construction", "maintenance"})

ATTRIBUTION = (
    "Contains Translink data © State of Queensland (Department of Transport and Main "
    "Roads), licensed under Creative Commons Attribution 4.0."
)
DISCLAIMER = (
    "BrisPulse is an independent project, not affiliated with or endorsed by Translink or "
    "the State of Queensland, which give no warranty about the accuracy, completeness or "
    "currency of the data."
)


class NotFoundError(Exception):
    """The requested route or trip does not exist."""


@dataclass(frozen=True, slots=True)
class View[T]:
    data: T | None
    feeds: tuple[FeedName, ...]
    notes: list[str] = field(default_factory=list)


def _notes(context: Context, *feeds: FeedName) -> list[str]:
    return [note for feed in feeds for note in context.feed_notes(feed)]


# --- shared builders --------------------------------------------------------------


def _route_ref(reference: Reference, route_id: str) -> RouteRef:
    route = reference.routes.get(route_id)
    return RouteRef(
        route_id=route_id,
        short_name=route.short_name if route else None,
        long_name=route.long_name if route else None,
        mode=route.mode if route else None,
    )


def _stop_ref(reference: Reference, stop_id: str | None) -> StopRef | None:
    if not stop_id:
        return None
    stop = reference.stops.get(stop_id)
    return StopRef(stop_id=stop_id, name=stop.name if stop else None)


def _running_delays(context: Context) -> dict[str, int | None]:
    """Predicted delay per running trip. Empty when running trips cannot be determined."""
    return {r.trip.trip_id: r.trip.next_stop_delay_s for r in context.running or []}


def _vehicle_out(
    context: Context, reference: Reference, vehicle: Vehicle, delays: dict[str, int | None]
) -> VehicleOut:
    route = reference.routes.get(vehicle.route_id) if vehicle.route_id else None
    return VehicleOut(
        vehicle_id=vehicle.vehicle_id,
        label=vehicle.label,
        lat=vehicle.lat,
        lon=vehicle.lon,
        mode=vehicle.mode,
        route_id=vehicle.route_id,
        route_short_name=route.short_name if route else None,
        trip_id=vehicle.trip_id,
        headsign=reference.trip_headsigns.get(vehicle.trip_id) if vehicle.trip_id else None,
        status=vehicle.status,
        stop=_stop_ref(reference, vehicle.stop_id),
        reported_at=context.at(vehicle.timestamp),
        fresh=vehicle.fresh,
        matched=vehicle.matched,
        predicted_delay_s=delays.get(vehicle.trip_id) if vehicle.trip_id else None,
    )


def _alert_out(context: Context, reference: Reference, alert: Alert) -> AlertOut:
    return AlertOut(
        alert_id=alert.alert_id,
        cause=alert.cause,
        effect=alert.effect,
        planned_works=alert.cause in PLANNED_WORKS_CAUSES,
        active=alert.is_active(context.now),
        header=alert.header,
        description=alert.description,
        url=alert.url,
        active_periods=[
            ActivePeriodOut(start=context.local(period.start), end=context.local(period.end))
            for period in alert.active_periods
        ],
        routes=[_route_ref(reference, route_id) for route_id in alert.route_ids],
        stops=[
            ref for stop_id in alert.stop_ids if (ref := _stop_ref(reference, stop_id)) is not None
        ],
    )


def _scheduled_start(context: Context, trip: TripState) -> dt.datetime | None:
    if trip.start_date is None or trip.start_time_s is None:
        return None
    return context.at(service_start_epoch(trip.start_date, trip.start_time_s, context.timezone))


def _delay_out(summary: DelaySummary) -> DelaySummaryOut:
    return DelaySummaryOut(
        sample_size=summary.sample_size,
        excluded_implausible=summary.excluded_implausible,
        without_delay=summary.without_delay,
        median_s=summary.median_s,
        p90_s=summary.p90_s,
        early=summary.early,
        within_band=summary.within_band,
        late=summary.late,
    )


# --- status -----------------------------------------------------------------------


def status(context: Context) -> View[StatusData]:
    feeds: dict[FeedName, FeedStatus] = {}
    for feed in FeedName:
        snapshot = context.snapshot(feed)
        attempt = context.last_attempts.get(feed)
        stats = snapshot.stats if snapshot else None
        feeds[feed] = FeedStatus(
            **context.feed_meta(feed).model_dump(),
            entity_count=stats.entity_count if stats else None,
            accepted=stats.accepted if stats else None,
            rejected=dict(stats.rejected) if stats else None,
            unmatched=stats.unmatched if stats else None,
            dropped_stale=stats.dropped_stale if stats else None,
            last_attempt_at=attempt.fetched_at.astimezone(context.timezone) if attempt else None,
            last_attempt_outcome=attempt.outcome.value if attempt else None,
        )
    reference = context.reference
    static = context.static_meta()
    settings = context.settings
    data = StatusData(
        feeds=feeds,
        static=(
            StaticStatus(
                **static.model_dump(),
                routes=len(reference.routes),
                stops=len(reference.stops),
                trips=len(reference.trip_headsigns),
            )
            if static is not None and reference is not None
            else None
        ),
        poll_interval_seconds={
            VP: settings.poll_vehicle_positions_seconds,
            TU: settings.poll_trip_updates_seconds,
            ALERTS: settings.poll_alerts_seconds,
        },
    )
    notes = _notes(context, *FeedName)
    if reference is None:
        notes.append("The static schedule has not been imported yet.")
    return View(data, tuple(FeedName), notes)


# --- overview ---------------------------------------------------------------------


def overview(context: Context) -> View[OverviewData]:
    vehicles = context.usable(VP)
    trips = context.usable(TU)
    alerts = context.usable(ALERTS)
    running = context.running

    vehicle_overview = None
    if vehicles is not None:
        fresh = [v for v in vehicles.items if v.fresh]
        vehicle_overview = VehicleOverview(
            fresh=len(fresh),
            last_seen=len(vehicles.items) - len(fresh),
            fresh_by_mode=dict(Counter(v.mode or "unknown" for v in fresh)),
        )

    trip_overview = None
    if running is not None and trips is not None:
        by_mode: dict[str, list[Any]] = {}
        for item in running:
            by_mode.setdefault(item.trip.mode or "unknown", []).append(item)
        trip_overview = TripOverview(
            running=len(running),
            running_by_mode={mode: len(items) for mode, items in by_mode.items()},
            canceled=trips.stats.canceled,
            delay=_delay_out(summarise_delays(running, context.thresholds)),
            delay_by_mode={
                mode: _delay_out(summarise_delays(items, context.thresholds))
                for mode, items in by_mode.items()
            },
        )

    alert_overview = None
    if alerts is not None:
        active = [a for a in alerts.items if a.is_active(context.now)]
        planned = sum(1 for a in active if a.cause in PLANNED_WORKS_CAUSES)
        alert_overview = AlertOverview(
            in_feed=len(alerts.items),
            active=len(active),
            active_planned_works=planned,
            active_other=len(active) - planned,
        )

    notes = _notes(context, VP, TU, ALERTS)
    if trip_overview is not None:
        notes.append(
            "Delay figures are TransLink's predictions for the next stop of trips that are "
            "running. They are not observed arrivals and not on-time performance."
        )
    data = OverviewData(vehicles=vehicle_overview, trips=trip_overview, alerts=alert_overview)
    return View(data, (VP, TU, ALERTS), notes)


# --- vehicles ---------------------------------------------------------------------


def vehicles(
    context: Context,
    reference: Reference,
    *,
    mode: str | None = None,
    route_id: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    fresh_only: bool = False,
) -> View[list[VehicleOut]]:
    notes = _notes(context, VP, TU)
    snapshot = context.usable(VP)
    if snapshot is None:
        return View(None, (VP, TU), notes)
    delays = _running_delays(context)
    selected: list[VehicleOut] = []
    for vehicle in snapshot.items:
        if mode is not None and vehicle.mode != mode:
            continue
        if route_id is not None and vehicle.route_id != route_id:
            continue
        if fresh_only and not vehicle.fresh:
            continue
        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = bbox
            if not (min_lon <= vehicle.lon <= max_lon and min_lat <= vehicle.lat <= max_lat):
                continue
        selected.append(_vehicle_out(context, reference, vehicle, delays))
    if context.running is None:
        notes.append("predicted_delay_s is null for every vehicle: trip updates are unavailable.")
    return View(selected, (VP, TU), notes)


# --- alerts -----------------------------------------------------------------------


def alerts(
    context: Context,
    reference: Reference,
    *,
    active: bool | None = None,
    route_id: str | None = None,
    stop_id: str | None = None,
) -> View[list[AlertOut]]:
    notes = _notes(context, ALERTS)
    snapshot = context.usable(ALERTS)
    if snapshot is None:
        return View(None, (ALERTS,), notes)
    selected = [
        _alert_out(context, reference, alert)
        for alert in snapshot.items
        if (active is None or alert.is_active(context.now) == active)
        and (route_id is None or route_id in alert.route_ids)
        and (stop_id is None or stop_id in alert.stop_ids)
    ]
    # Active alerts first; within each group, a stable order by ID.
    selected.sort(key=lambda a: (not a.active, a.alert_id))
    return View(selected, (ALERTS,), notes)


# --- routes -----------------------------------------------------------------------


def _route_counts(
    context: Context,
) -> tuple[Counter[str] | None, Counter[str] | None, Counter[str] | None]:
    """Per-route counts of fresh vehicles, running trips and active alerts."""
    vehicle_snapshot = context.usable(VP)
    alert_snapshot = context.usable(ALERTS)
    running = context.running
    fresh = (
        Counter(v.route_id for v in vehicle_snapshot.items if v.fresh and v.route_id)
        if vehicle_snapshot is not None
        else None
    )
    trips = (
        Counter(r.trip.route_id for r in running if r.trip.route_id)
        if running is not None
        else None
    )
    active = (
        Counter(
            route_id
            for alert in alert_snapshot.items
            if alert.is_active(context.now)
            for route_id in alert.route_ids
        )
        if alert_snapshot is not None
        else None
    )
    return fresh, trips, active


def _route_summary(
    reference: Reference,
    route_id: str,
    counts: tuple[Counter[str] | None, Counter[str] | None, Counter[str] | None],
) -> RouteSummary:
    route = reference.routes[route_id]
    fresh, trips, active = counts
    return RouteSummary(
        route_id=route_id,
        short_name=route.short_name,
        long_name=route.long_name,
        mode=route.mode,
        color=route.color,
        text_color=route.text_color,
        # A Counter answers 0 for a route with none: a real zero, known from live data.
        vehicles_fresh=fresh[route_id] if fresh is not None else None,
        trips_running=trips[route_id] if trips is not None else None,
        alerts_active=active[route_id] if active is not None else None,
    )


def routes(
    context: Context, reference: Reference, *, mode: str | None = None
) -> View[list[RouteSummary]]:
    counts = _route_counts(context)
    selected = [
        _route_summary(reference, route_id, counts)
        for route_id, route in reference.routes.items()
        if mode is None or route.mode == mode
    ]
    selected.sort(key=lambda r: (r.mode or "", r.short_name or "", r.route_id))
    return View(selected, (VP, TU, ALERTS), _notes(context, VP, TU, ALERTS))


def _trip_brief(context: Context, reference: Reference, running: RunningTrip) -> TripBrief:
    trip = running.trip
    first_stop = trip.predictions[0].stop_id if trip.predictions else None
    return TripBrief(
        trip_id=trip.trip_id,
        headsign=reference.trip_headsigns.get(trip.trip_id),
        relationship=trip.relationship,
        scheduled_start=_scheduled_start(context, trip),
        # From the vehicle feed: some trip updates (a replacement rail trip, when
        # observed) do not name their vehicle.
        vehicle_id=running.vehicle.vehicle_id,
        predicted_delay_s=trip.next_stop_delay_s,
        delay_implausible=trip.delay_implausible,
        next_stop=_stop_ref(reference, first_stop),
    )


def route_detail(context: Context, reference: Reference, route_id: str) -> View[RouteDetail]:
    if route_id not in reference.routes:
        raise NotFoundError(f"No route {route_id!r} in the current schedule.")
    vehicle_view = vehicles(context, reference, route_id=route_id)
    alert_view = alerts(context, reference, route_id=route_id)
    running = context.running
    data = RouteDetail(
        route=_route_summary(reference, route_id, _route_counts(context)),
        vehicles=vehicle_view.data,
        running_trips=(
            [_trip_brief(context, reference, r) for r in running if r.trip.route_id == route_id]
            if running is not None
            else None
        ),
        alerts=alert_view.data,
    )
    return View(data, (VP, TU, ALERTS), _notes(context, VP, TU, ALERTS))


# --- trips ------------------------------------------------------------------------


def trip_detail(context: Context, reference: Reference, trip_id: str) -> View[TripDetail]:
    notes = _notes(context, VP, TU)
    snapshot = context.usable(TU)
    trip: TripState | None = None
    if snapshot is not None:
        trip = next((t for t in snapshot.items if t.trip_id == trip_id), None)
    in_schedule = reference.has_trip(trip_id)
    if trip is None and not in_schedule:
        raise NotFoundError(f"No trip {trip_id!r} in the current schedule or real-time data.")

    realtime = None
    if trip is not None:
        running = context.running
        match = next((r for r in running or [] if r.trip.trip_id == trip_id), None)
        realtime = TripRealtime(
            relationship=trip.relationship,
            scheduled_start=_scheduled_start(context, trip),
            running=(match is not None) if running is not None else None,
            vehicle_id=match.vehicle.vehicle_id if match is not None else trip.vehicle_id,
            updated_at=context.local(trip.timestamp),
            predicted_delay_s=trip.next_stop_delay_s,
            delay_implausible=trip.delay_implausible,
            stops=[
                StopPredictionOut(
                    stop=StopRef(
                        stop_id=p.stop_id,
                        name=s.name if (s := reference.stops.get(p.stop_id)) else None,
                    ),
                    stop_sequence=p.stop_sequence,
                    arrival_time=context.local(p.arrival_time),
                    arrival_delay_s=p.arrival_delay_s,
                    departure_time=context.local(p.departure_time),
                    departure_delay_s=p.departure_delay_s,
                )
                for p in trip.predictions
            ],
        )
    elif snapshot is not None:
        notes.append("This trip is in the schedule but has no real-time data right now.")

    route_id = trip.route_id if trip is not None else None
    data = TripDetail(
        trip_id=trip_id,
        in_schedule=in_schedule,
        route=_route_ref(reference, route_id) if route_id else None,
        headsign=reference.trip_headsigns.get(trip_id),
        realtime=realtime,
    )
    return View(data, (VP, TU), notes)


# --- metric definitions -----------------------------------------------------------


def metric_definitions(context: Context) -> MetricsData:
    t = context.thresholds
    source = "TransLink GTFS-Realtime, South East Queensland"
    return MetricsData(
        metrics=[
            MetricDefinition(
                name="Fresh vehicles",
                definition=(
                    f"Vehicles whose position report is at most {t.vehicle_fresh_s} s older "
                    "than the feed it arrived in. Older reports, up to "
                    f"{t.vehicle_drop_s} s, are 'last seen' and are not counted."
                ),
                source=f"{source}: VehiclePositions",
                limitations=(
                    "Counts vehicles that report. About 8 % of scheduled trips in progress "
                    "had no vehicle record when measured on 2026-11-16, so this is a lower "
                    "bound, not the number of vehicles in service."
                ),
            ),
            MetricDefinition(
                name="Running trips",
                definition=(
                    "Trips that are in the static schedule, are not cancelled, have passed "
                    "their scheduled start, and have a fresh vehicle reporting."
                ),
                source=f"{source}: TripUpdates and VehiclePositions",
                limitations=(
                    "Trips without a reporting vehicle are not counted even if they are operating."
                ),
            ),
            MetricDefinition(
                name="Predicted delay",
                definition=(
                    "TransLink's predicted delay at the next stop of each running trip; "
                    "positive is late. Summarised as the median and 90th percentile "
                    "(nearest rank) and as counts early (more than "
                    f"{t.delay_early_s} s), late (more than {t.delay_late_s} s) and within "
                    f"that band. Delays beyond ±{t.delay_plausible_s} s are excluded and "
                    f"counted. Medians need at least {t.min_sample} trips."
                ),
                source=f"{source}: TripUpdates",
                limitations=(
                    "A prediction made mid-trip, not an observed arrival. It is not "
                    "on-time performance and is not comparable to TransLink's published "
                    "punctuality figures. The band limits are BrisPulse's own."
                ),
            ),
            MetricDefinition(
                name="Active alerts",
                definition=(
                    "Service alerts with an active period that contains the present "
                    "moment. Alerts whose stated cause is construction or maintenance are "
                    "labelled planned works."
                ),
                source=f"{source}: Alerts",
                limitations=(
                    "An alert that is not labelled planned works is not necessarily an "
                    "incident: timetable changes and general notices are filed under other "
                    "causes. Alerts name routes and stops, never individual trips."
                ),
            ),
        ],
        thresholds={
            "vehicle_fresh_s": t.vehicle_fresh_s,
            "vehicle_drop_s": t.vehicle_drop_s,
            "delay_early_s": t.delay_early_s,
            "delay_late_s": t.delay_late_s,
            "delay_plausible_s": t.delay_plausible_s,
            "min_sample": t.min_sample,
        },
        freshness_limits_seconds={
            feed: {
                "live": limits.live_s,
                "delayed": limits.delayed_s,
                "stale": limits.stale_s,
            }
            for feed, limits in FRESHNESS_LIMITS.items()
        },
        attribution=ATTRIBUTION,
        disclaimer=DISCLAIMER,
    )
