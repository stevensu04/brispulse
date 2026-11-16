"""Turn decoded Protobuf feeds into validated records (architecture §5.3).

Rules, in short:

* A record that cannot be used is rejected and counted under a reason.
* A record that is usable but does not resolve in the static schedule is kept and
  marked unmatched, so it can be shown but stays out of metrics.
* Nothing is corrected or filled in. A missing value stays missing.
"""

import datetime as dt
from collections import Counter
from typing import Any, Literal

from google.transit import gtfs_realtime_pb2 as pb

from brispulse.gtfs_static.parse import parse_gtfs_date, parse_gtfs_time
from brispulse.realtime.model import (
    ActivePeriod,
    Alert,
    FeedStats,
    StopPrediction,
    TripState,
    Vehicle,
)
from brispulse.realtime.reference import Reference
from brispulse.realtime.thresholds import Thresholds


def _enum_name(enum_type: Any, value: int) -> str:
    try:
        return str(enum_type.Name(value)).lower()
    except ValueError:
        return "unknown"


def normalise_vehicles(
    message: pb.FeedMessage, reference: Reference, thresholds: Thresholds
) -> tuple[tuple[Vehicle, ...], FeedStats]:
    header_timestamp: int = message.header.timestamp
    rejected: Counter[str] = Counter()
    vehicles: list[Vehicle] = []
    seen: set[str] = set()
    unmatched = dropped_stale = 0

    for entity in message.entity:
        if not entity.HasField("vehicle"):
            rejected["not_a_vehicle"] += 1
            continue
        record = entity.vehicle

        if not record.HasField("position"):
            rejected["bad_position"] += 1
            continue
        lat, lon = record.position.latitude, record.position.longitude
        inside = (
            thresholds.lat_min <= lat <= thresholds.lat_max
            and thresholds.lon_min <= lon <= thresholds.lon_max
        )
        if not inside:
            rejected["bad_position"] += 1
            continue

        timestamp: int = record.timestamp
        if not timestamp or timestamp > header_timestamp + thresholds.future_tolerance_s:
            rejected["bad_timestamp"] += 1
            continue

        vehicle_id = record.vehicle.id or entity.id
        if not vehicle_id:
            rejected["missing_id"] += 1
            continue
        if vehicle_id in seen:
            rejected["duplicate_id"] += 1
            continue
        seen.add(vehicle_id)

        age = max(0, header_timestamp - timestamp)
        if age > thresholds.vehicle_drop_s:
            # Not an error: the vehicle simply has not reported for a long time.
            dropped_stale += 1
            continue

        trip_id = record.trip.trip_id or None
        route_id = record.trip.route_id or None
        mode = reference.route_modes.get(route_id) if route_id else None
        matched = trip_id in reference.trip_ids and mode is not None
        if not matched:
            unmatched += 1

        vehicles.append(
            Vehicle(
                vehicle_id=vehicle_id,
                label=record.vehicle.label or None,
                trip_id=trip_id,
                route_id=route_id,
                mode=mode,
                lat=lat,
                lon=lon,
                status=(
                    _enum_name(pb.VehiclePosition.VehicleStopStatus, record.current_status)
                    if record.HasField("current_status")
                    else None
                ),
                stop_id=record.stop_id or None,
                stop_sequence=(
                    record.current_stop_sequence
                    if record.HasField("current_stop_sequence")
                    else None
                ),
                timestamp=timestamp,
                age_s=age,
                fresh=age <= thresholds.vehicle_fresh_s,
                matched=matched,
            )
        )

    stats = FeedStats(
        entity_count=len(message.entity),
        accepted=len(vehicles),
        rejected=dict(rejected),
        unmatched=unmatched,
        dropped_stale=dropped_stale,
    )
    return tuple(vehicles), stats


def _event(
    update: pb.TripUpdate.StopTimeUpdate, name: Literal["arrival", "departure"]
) -> tuple[int | None, int | None]:
    """(time, delay) of a stop-time event, each None when the feed does not give it."""
    if not update.HasField(name):
        return None, None
    event = getattr(update, name)
    return (
        event.time if event.HasField("time") else None,
        event.delay if event.HasField("delay") else None,
    )


def _next_stop_delay(predictions: list[StopPrediction]) -> int | None:
    """Delay at the first listed stop that carries one.

    TransLink drops passed stops from a trip update, so the first listed stop is the
    current or next one (true for 87 % of trips when measured on 2026-11-16).
    """
    for prediction in predictions:
        if prediction.arrival_delay_s is not None:
            return prediction.arrival_delay_s
        if prediction.departure_delay_s is not None:
            return prediction.departure_delay_s
    return None


def _start_date(text: str) -> dt.date | None:
    try:
        return parse_gtfs_date(text) if text else None
    except ValueError:
        return None


def _start_time(text: str) -> int | None:
    try:
        return parse_gtfs_time(text) if text else None
    except ValueError:
        return None


def normalise_trip_updates(
    message: pb.FeedMessage, reference: Reference, thresholds: Thresholds
) -> tuple[tuple[TripState, ...], FeedStats]:
    rejected: Counter[str] = Counter()
    trips: dict[str, TripState] = {}
    unmatched = implausible = canceled = 0

    for entity in message.entity:
        if not entity.HasField("trip_update"):
            rejected["not_a_trip_update"] += 1
            continue
        update = entity.trip_update
        trip_id = update.trip.trip_id
        if not trip_id:
            rejected["missing_trip_id"] += 1
            continue
        if trip_id in trips:
            rejected["duplicate_trip"] += 1
            continue

        predictions: list[StopPrediction] = []
        for stop_update in update.stop_time_update:
            arrival_time, arrival_delay = _event(stop_update, "arrival")
            departure_time, departure_delay = _event(stop_update, "departure")
            predictions.append(
                StopPrediction(
                    stop_id=stop_update.stop_id,
                    stop_sequence=(
                        stop_update.stop_sequence if stop_update.HasField("stop_sequence") else None
                    ),
                    arrival_time=arrival_time,
                    arrival_delay_s=arrival_delay,
                    departure_time=departure_time,
                    departure_delay_s=departure_delay,
                )
            )

        delay = _next_stop_delay(predictions)
        delay_implausible = delay is not None and abs(delay) > thresholds.delay_plausible_s
        relationship = _enum_name(
            pb.TripDescriptor.ScheduleRelationship, update.trip.schedule_relationship
        )
        route_id = update.trip.route_id or None
        mode = reference.route_modes.get(route_id) if route_id else None
        matched = trip_id in reference.trip_ids and mode is not None

        unmatched += not matched
        implausible += delay_implausible
        canceled += relationship == "canceled"

        trips[trip_id] = TripState(
            trip_id=trip_id,
            route_id=route_id,
            mode=mode,
            start_date=_start_date(update.trip.start_date),
            start_time_s=_start_time(update.trip.start_time),
            relationship=relationship,
            vehicle_id=update.vehicle.id or None if update.HasField("vehicle") else None,
            timestamp=update.timestamp or None,
            next_stop_delay_s=delay,
            delay_implausible=delay_implausible,
            predictions=tuple(predictions),
            matched=matched,
        )

    stats = FeedStats(
        entity_count=len(message.entity),
        accepted=len(trips),
        rejected=dict(rejected),
        unmatched=unmatched,
        implausible_delays=implausible,
        canceled=canceled,
    )
    return tuple(trips.values()), stats


def _translated(text: pb.TranslatedString) -> str | None:
    """Pick the English translation, else the first one given."""
    translations = list(text.translation)
    if not translations:
        return None
    for translation in translations:
        if translation.language.lower().startswith("en"):
            return translation.text.strip() or None
    return translations[0].text.strip() or None


def normalise_alerts(
    message: pb.FeedMessage, reference: Reference
) -> tuple[tuple[Alert, ...], FeedStats]:
    rejected: Counter[str] = Counter()
    alerts: dict[str, Alert] = {}
    unmatched = 0

    for entity in message.entity:
        if not entity.HasField("alert"):
            rejected["not_an_alert"] += 1
            continue
        if not entity.id:
            rejected["missing_id"] += 1
            continue
        if entity.id in alerts:
            rejected["duplicate_id"] += 1
            continue
        record = entity.alert

        # dict.fromkeys keeps feed order while removing repeats.
        route_ids = tuple(dict.fromkeys(e.route_id for e in record.informed_entity if e.route_id))
        stop_ids = tuple(dict.fromkeys(e.stop_id for e in record.informed_entity if e.stop_id))
        unresolved_routes = tuple(r for r in route_ids if r not in reference.route_modes)
        unresolved_stops = tuple(s for s in stop_ids if s not in reference.stop_ids)
        if unresolved_routes or unresolved_stops:
            # The alert itself is still valid and is kept.
            unmatched += 1

        alerts[entity.id] = Alert(
            alert_id=entity.id,
            cause=_enum_name(pb.Alert.Cause, record.cause),
            effect=_enum_name(pb.Alert.Effect, record.effect),
            header=_translated(record.header_text),
            description=_translated(record.description_text),
            url=_translated(record.url),
            active_periods=tuple(
                ActivePeriod(
                    start=period.start if period.HasField("start") else None,
                    end=period.end if period.HasField("end") else None,
                )
                for period in record.active_period
            ),
            route_ids=route_ids,
            stop_ids=stop_ids,
            unresolved_route_ids=unresolved_routes,
            unresolved_stop_ids=unresolved_stops,
        )

    stats = FeedStats(
        entity_count=len(message.entity),
        accepted=len(alerts),
        rejected=dict(rejected),
        unmatched=unmatched,
    )
    return tuple(alerts.values()), stats
