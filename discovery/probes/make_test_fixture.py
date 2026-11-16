"""Cut a small, real test fixture out of a saved set of TransLink feeds.

Usage: make_test_fixture.py <static_dir> <realtime_dir> <output_dir>

Keeps a sample of trips that covers the cases the collector must handle (running,
not started with and without a vehicle, stale vehicles, a cancelled trip, replacement
trips, a trip with two vehicles) and writes the matching static IDs next to them.
"""

import csv
import json
import sys
from pathlib import Path

from google.transit import gtfs_realtime_pb2 as pb

static_dir, realtime_dir, output_dir = (Path(arg) for arg in sys.argv[1:4])
MODES = {"0": "tram", "2": "rail", "3": "bus", "4": "ferry"}


def load(name: str) -> pb.FeedMessage:
    message = pb.FeedMessage()
    message.ParseFromString((realtime_dir / f"{name}.pb").read_bytes())
    return message


def seconds(text: str) -> int:
    hours, minutes, secs = text.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + int(secs)


vehicles, trips, alerts = load("VehiclePositions"), load("TripUpdates"), load("Alerts")
header = vehicles.header.timestamp
by_trip: dict[str, list[pb.FeedEntity]] = {}
for entity in vehicles.entity:
    by_trip.setdefault(entity.vehicle.trip.trip_id, []).append(entity)

keep: list[str] = []


def take(candidates: list[str], limit: int) -> None:
    for trip_id in candidates:
        if limit == 0:
            return
        if trip_id not in keep:
            keep.append(trip_id)
            limit -= 1


def age(trip_id: str) -> int:
    return min(header - e.vehicle.timestamp for e in by_trip[trip_id])


updates = {e.trip_update.trip.trip_id: e for e in trips.entity}
# Brisbane is UTC+10 all year; good enough to split "started" from "not started" here.
now_s = (trips.header.timestamp + 10 * 3600) % 86400
started = {t for t, e in updates.items() if seconds(e.trip_update.trip.start_time) <= now_s}
order = list(updates)
take([t for t in order if updates[t].trip_update.trip.schedule_relationship == 3], 5)
take([t for t in order if updates[t].trip_update.trip.schedule_relationship == 5], 6)
take([t for t in order if len(by_trip.get(t, [])) > 1], 6)
take([t for t in order if t in by_trip and 90 < age(t) <= 900], 6)
take([t for t in order if t in by_trip and age(t) > 900], 6)
take([t for t in order if t not in started and t in by_trip and age(t) <= 90], 15)
take([t for t in order if t not in started and t not in by_trip], 25)
take([t for t in order if t in started and t not in by_trip], 6)
take([t for t in order if t in started and t in by_trip and age(t) <= 90], 60)

output_dir.mkdir(parents=True, exist_ok=True)


def write(name: str, source: pb.FeedMessage, entities: list[pb.FeedEntity]) -> None:
    message = pb.FeedMessage()
    message.header.CopyFrom(source.header)
    message.entity.extend(entities)
    (output_dir / name).write_bytes(message.SerializeToString())


kept_vehicles = [e for t in keep for e in by_trip.get(t, [])]
kept_updates = [updates[t] for t in keep]
write("vehicle_positions.pb", vehicles, kept_vehicles)
write("trip_updates.pb", trips, kept_updates)
write("alerts.pb", alerts, list(alerts.entity))


def column(file: str, name: str) -> set[str]:
    with (static_dir / file).open(newline="", encoding="utf-8-sig") as handle:
        return {row[name] for row in csv.DictReader(handle)}


with (static_dir / "routes.txt").open(newline="", encoding="utf-8-sig") as handle:
    all_modes = {row["route_id"]: MODES[row["route_type"]] for row in csv.DictReader(handle)}
used_routes = {e.vehicle.trip.route_id for e in kept_vehicles}
used_routes |= {e.trip_update.trip.route_id for e in kept_updates}
alert_routes = {i.route_id for e in alerts.entity for i in e.alert.informed_entity if i.route_id}
alert_stops = {i.stop_id for e in alerts.entity for i in e.alert.informed_entity if i.stop_id}
reference = {
    "route_modes": {r: all_modes[r] for r in sorted((used_routes | alert_routes) & set(all_modes))},
    "trip_ids": sorted(set(keep) & column("trips.txt", "trip_id")),
    "stop_ids": sorted(alert_stops & column("stops.txt", "stop_id")),
}
(output_dir / "reference.json").write_text(json.dumps(reference, indent=1) + "\n")
print(f"trips kept: {len(keep)}; vehicles: {len(kept_vehicles)}; alerts: {len(alerts.entity)}")
for path in sorted(output_dir.iterdir()):
    print(f"  {path.name}: {path.stat().st_size} bytes")
