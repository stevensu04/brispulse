"""Builds GTFS-Realtime messages for tests.

Every builder returns Protobuf objects, so a test states only what matters to it and
gets a well-formed message around it. ``NOW`` is the feed's own clock in these tests:
Monday 2026-11-16, 09:00:00 in Brisbane.
"""

import datetime as dt
from typing import Any

from google.transit import gtfs_realtime_pb2 as pb

from brispulse.realtime.reference import Reference, RouteInfo, StopInfo

BRISBANE = dt.timezone(dt.timedelta(hours=10))
NOW = int(dt.datetime(2026, 11, 16, 9, 0, 0, tzinfo=BRISBANE).timestamp())

REFERENCE = Reference(
    version_id=7,
    routes={
        "R1": RouteInfo("100", "City Loop", "bus", "00FF00", "000000"),
        "R2": RouteInfo("BNSH", "Northern Line", "rail", None, None),
    },
    trip_headsigns={"T1": "City", "T2": "Northside", "T3": "City", "T4": None},
    stops={
        "S1": StopInfo("First Street", -27.47, 153.02),
        "S2": StopInfo("Second Street", -27.48, 153.03),
    },
    published_at=dt.datetime(2026, 11, 13, 19, 45, 24, tzinfo=dt.UTC),
    feed_start_date=dt.date(2026, 11, 14),
    feed_end_date=dt.date(2027, 1, 13),
)

SCHEDULED = pb.TripDescriptor.SCHEDULED
CANCELED = pb.TripDescriptor.CANCELED
REPLACEMENT = pb.TripDescriptor.REPLACEMENT


def feed(*entities: Any, timestamp: int | None = NOW, version: str = "2.0") -> Any:
    message = pb.FeedMessage()
    message.header.gtfs_realtime_version = version
    if timestamp is not None:
        message.header.timestamp = timestamp
    for entity in entities:
        message.entity.append(entity)
    return message


def feed_bytes(*entities: Any, timestamp: int | None = NOW, version: str = "2.0") -> bytes:
    return bytes(feed(*entities, timestamp=timestamp, version=version).SerializeToString())


def vehicle(
    vehicle_id: str = "V1",
    *,
    trip_id: str = "T1",
    route_id: str = "R1",
    lat: float | None = -27.47,
    lon: float | None = 153.02,
    age_s: int = 10,
    timestamp: int | None = None,
    stop_id: str = "S1",
    stop_sequence: int | None = 3,
    label: str = "",
) -> Any:
    entity = pb.FeedEntity()
    entity.id = f"VU-{vehicle_id}"
    record = entity.vehicle
    record.vehicle.id = vehicle_id
    if label:
        record.vehicle.label = label
    if trip_id:
        record.trip.trip_id = trip_id
    if route_id:
        record.trip.route_id = route_id
    if lat is not None and lon is not None:
        record.position.latitude = lat
        record.position.longitude = lon
    record.timestamp = NOW - age_s if timestamp is None else timestamp
    record.current_status = pb.VehiclePosition.STOPPED_AT
    if stop_id:
        record.stop_id = stop_id
    if stop_sequence is not None:
        record.current_stop_sequence = stop_sequence
    return entity


def trip_update(
    trip_id: str = "T1",
    *,
    route_id: str = "R1",
    start_date: str = "20261116",
    start_time: str = "08:30:00",
    relationship: Any = SCHEDULED,
    vehicle_id: str = "V1",
    # (stop_id, stop_sequence, arrival_delay, departure_delay); None omits that event.
    stops: tuple[tuple[str, int, int | None, int | None], ...] = (("S1", 3, 120, 130),),
) -> Any:
    entity = pb.FeedEntity()
    entity.id = f"TU-{trip_id}"
    update = entity.trip_update
    if trip_id:
        update.trip.trip_id = trip_id
    if route_id:
        update.trip.route_id = route_id
    if start_date:
        update.trip.start_date = start_date
    if start_time:
        update.trip.start_time = start_time
    update.trip.schedule_relationship = relationship
    if vehicle_id:
        update.vehicle.id = vehicle_id
    update.timestamp = NOW - 20
    for stop_id, sequence, arrival_delay, departure_delay in stops:
        stop_update = update.stop_time_update.add()
        stop_update.stop_id = stop_id
        stop_update.stop_sequence = sequence
        if arrival_delay is not None:
            stop_update.arrival.delay = arrival_delay
            stop_update.arrival.time = NOW + 300 + arrival_delay
        if departure_delay is not None:
            stop_update.departure.delay = departure_delay
            stop_update.departure.time = NOW + 300 + departure_delay
    return entity


def alert(
    alert_id: str = "A1",
    *,
    periods: tuple[tuple[int | None, int | None], ...] = ((NOW - 3600, NOW + 3600),),
    route_ids: tuple[str, ...] = ("R1",),
    stop_ids: tuple[str, ...] = (),
    cause: Any = pb.Alert.CONSTRUCTION,
    effect: Any = pb.Alert.STOP_MOVED,
    header: str = "Stop moved",
    description: str = "Use the temporary stop.",
    language: str = "en-AU",
) -> Any:
    entity = pb.FeedEntity()
    entity.id = alert_id
    record = entity.alert
    for start, end in periods:
        period = record.active_period.add()
        if start is not None:
            period.start = start
        if end is not None:
            period.end = end
    for route_id in route_ids:
        record.informed_entity.add().route_id = route_id
    for stop_id in stop_ids:
        record.informed_entity.add().stop_id = stop_id
    record.cause = cause
    record.effect = effect
    for target, text in ((record.header_text, header), (record.description_text, description)):
        if text:
            translation = target.translation.add()
            translation.text = text
            translation.language = language
    return entity
