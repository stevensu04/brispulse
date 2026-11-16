"""HTTP endpoints. Each one is thin: gather a context, build a view, send it."""

import hashlib
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse

from brispulse.api import views
from brispulse.api.context import Context
from brispulse.api.errors import ApiError
from brispulse.api.schemas import (
    AlertOut,
    Envelope,
    ErrorResponse,
    Meta,
    MetricsData,
    OverviewData,
    RouteDetail,
    RouteSummary,
    StatusData,
    TripDetail,
    VehicleOut,
)
from brispulse.config import get_settings
from brispulse.realtime.reference import Reference

router = APIRouter(prefix="/api/v1")

Mode = Literal["bus", "rail", "ferry", "tram"]

# TransLink refreshes its feeds every 10-30 s; caching for less would only add load.
LIVE_MAX_AGE_S = 10
REFERENCE_MAX_AGE_S = 300

_ERRORS: dict[int | str, dict[str, Any]] = {
    503: {"model": ErrorResponse, "description": "The service is not ready yet."},
}
_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    **_ERRORS,
    404: {"model": ErrorResponse, "description": "No such route or trip."},
}


def get_context(request: Request) -> Context:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise ApiError(503, "not_ready", "The service is starting.")
    return Context(
        # Captured once: the collector may publish new data while this request runs.
        state=runtime.live.current,
        last_attempts=dict(runtime.live.last_attempts),
        reference=runtime.reference.current,
        now=request.app.state.clock(),
        settings=request.app.state.settings or get_settings(),
        latest_samples=runtime.history.latest_samples if runtime.history is not None else (),
    )


def get_reference(context: Annotated[Context, Depends(get_context)]) -> Reference:
    if context.reference is None:
        raise ApiError(503, "schedule_not_loaded", "The static schedule has not been imported yet.")
    return context.reference


ContextDep = Annotated[Context, Depends(get_context)]
ReferenceDep = Annotated[Reference, Depends(get_reference)]


def respond(
    request: Request, context: Context, view: views.View[Any], max_age: int = LIVE_MAX_AGE_S
) -> Response:
    """Wrap a view in the envelope and add cache headers.

    The ETag changes whenever the underlying data or its freshness state changes. It is
    a weak validator: two responses with the same tag differ only in ``generated_at``
    and ``age_seconds``.
    """
    meta = Meta(
        generated_at=context.at(context.now),
        feeds={feed: context.feed_meta(feed) for feed in view.feeds},
        static_version=context.static_meta(),
        notes=view.notes,
    )
    fingerprint = [str(request.url), str(meta.static_version and meta.static_version.version_id)]
    fingerprint += [
        f"{feed.value}:{info.state.value}:{info.source_timestamp}"
        for feed, info in meta.feeds.items()
    ]
    etag = 'W/"' + hashlib.sha1("|".join(fingerprint).encode()).hexdigest()[:20] + '"'
    headers = {"Cache-Control": f"public, max-age={max_age}", "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    body = Envelope[Any](data=view.data, meta=meta).model_dump(mode="json")
    return JSONResponse(body, headers=headers)


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    try:
        min_lon, min_lat, max_lon, max_lat = (float(part) for part in value.split(","))
    except ValueError:
        raise ApiError(
            422, "invalid_request", "bbox must be four numbers: min_lon,min_lat,max_lon,max_lat."
        ) from None
    if min_lon > max_lon or min_lat > max_lat:
        raise ApiError(422, "invalid_request", "bbox minimums must not exceed its maximums.")
    return min_lon, min_lat, max_lon, max_lat


@router.get("/status", response_model=Envelope[StatusData])
def get_status(request: Request, context: ContextDep) -> Response:
    """State of each feed, the last fetch attempts and the schedule in use."""
    return respond(request, context, views.status(context))


@router.get("/overview", response_model=Envelope[OverviewData], responses=_ERRORS)
def get_overview(request: Request, context: ContextDep) -> Response:
    """Headline numbers for the network right now."""
    return respond(request, context, views.overview(context))


@router.get("/vehicles", response_model=Envelope[list[VehicleOut]], responses=_ERRORS)
def get_vehicles(
    request: Request,
    context: ContextDep,
    reference: ReferenceDep,
    mode: Mode | None = None,
    route_id: str | None = None,
    bbox: Annotated[str | None, Query(description="min_lon,min_lat,max_lon,max_lat")] = None,
    fresh_only: bool = False,
) -> Response:
    """Vehicle positions: fresh ones, and "last seen" ones unless ``fresh_only`` is set."""
    view = views.vehicles(
        context,
        reference,
        mode=mode,
        route_id=route_id,
        bbox=parse_bbox(bbox),
        fresh_only=fresh_only,
    )
    return respond(request, context, view)


@router.get("/routes", response_model=Envelope[list[RouteSummary]], responses=_ERRORS)
def get_routes(
    request: Request, context: ContextDep, reference: ReferenceDep, mode: Mode | None = None
) -> Response:
    """Every route in the schedule, with live counts where live data is available."""
    return respond(request, context, views.routes(context, reference, mode=mode))


@router.get("/routes/{route_id}", response_model=Envelope[RouteDetail], responses=_NOT_FOUND)
def get_route(
    request: Request, context: ContextDep, reference: ReferenceDep, route_id: str
) -> Response:
    """One route: its vehicles, running trips and alerts."""
    return respond(request, context, views.route_detail(context, reference, route_id))


@router.get("/trips/{trip_id}", response_model=Envelope[TripDetail], responses=_NOT_FOUND)
def get_trip(
    request: Request, context: ContextDep, reference: ReferenceDep, trip_id: str
) -> Response:
    """One trip: predicted times and delays at its upcoming stops."""
    return respond(request, context, views.trip_detail(context, reference, trip_id))


@router.get("/alerts", response_model=Envelope[list[AlertOut]], responses=_ERRORS)
def get_alerts(
    request: Request,
    context: ContextDep,
    reference: ReferenceDep,
    active: bool | None = None,
    route_id: str | None = None,
    stop_id: str | None = None,
) -> Response:
    """Service alerts, active ones first."""
    view = views.alerts(context, reference, active=active, route_id=route_id, stop_id=stop_id)
    return respond(request, context, view)


@router.get("/meta/metrics", response_model=Envelope[MetricsData])
def get_metric_definitions(request: Request, context: ContextDep) -> Response:
    """What each figure means, the limits in use, and the data attribution."""
    view = views.View(views.metric_definitions(context), feeds=())
    return respond(request, context, view, max_age=REFERENCE_MAX_AGE_S)
