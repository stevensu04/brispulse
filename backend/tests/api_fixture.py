"""Builds an application around a hand-made live state, for API tests.

The default "network" is small enough to reason about by hand:

* V1 on trip T1 (bus route R1), fresh, predicted 120 s late            -> running
* V2 on trip T2 (rail route R2), fresh, predicted 400 s late           -> running
* V3 on trip T3 (R1), last reported 300 s ago                          -> not running
* V4 on trip T404, which is not in the schedule                        -> unmatched
* trip T4 is cancelled
* alert A1: construction on R1 at stop S1, active
* alert A2: maintenance on R2, starts in an hour
* alert A3: other cause on R2 at a stop the schedule does not know, active
"""

from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient
from google.transit import gtfs_realtime_pb2 as pb

from brispulse.config import Settings
from brispulse.main import create_app
from brispulse.realtime.collector import LiveStateHolder
from brispulse.realtime.model import FeedName, FeedSnapshot
from brispulse.realtime.normalise import (
    normalise_alerts,
    normalise_trip_updates,
    normalise_vehicles,
)
from brispulse.realtime.reference import Reference
from brispulse.realtime.thresholds import DEFAULT_THRESHOLDS
from brispulse.runtime import Runtime
from tests.rt_fixture import CANCELED, NOW, REFERENCE, alert, feed, trip_update, vehicle

VP, TU, ALERTS = FeedName.VEHICLE_POSITIONS, FeedName.TRIP_UPDATES, FeedName.ALERTS

SETTINGS = Settings(database_url="postgresql://unused/unused", collector_enabled=False)

DEFAULT_VEHICLES = (
    vehicle("V1", trip_id="T1", route_id="R1", label="1001"),
    vehicle("V2", trip_id="T2", route_id="R2", lat=-27.60, lon=153.10, stop_id="S2"),
    vehicle("V3", trip_id="T3", route_id="R1", age_s=300),
    vehicle("V4", trip_id="T404", route_id="R1", stop_id="S404"),
)
DEFAULT_TRIPS = (
    trip_update("T1", vehicle_id="V1", stops=(("S1", 3, 120, 130), ("S2", 4, 110, 110))),
    trip_update("T2", route_id="R2", vehicle_id="V2", stops=(("S2", 5, 400, 400),)),
    trip_update("T3", vehicle_id="V3", stops=(("S1", 1, 0, 0),)),
    trip_update("T4", relationship=CANCELED, vehicle_id="", stops=()),
)
DEFAULT_ALERTS = (
    alert("A1", route_ids=("R1",), stop_ids=("S1",)),
    alert(
        "A2",
        route_ids=("R2",),
        periods=((NOW + 3600, NOW + 7200),),
        cause=pb.Alert.MAINTENANCE,
        effect=pb.Alert.REDUCED_SERVICE,
        header="Night works",
    ),
    alert(
        "A3",
        route_ids=("R2",),
        stop_ids=("S404",),
        cause=pb.Alert.OTHER_CAUSE,
        effect=pb.Alert.SIGNIFICANT_DELAYS,
        header="Delays",
    ),
)


@dataclass
class StubReference:
    current: Reference | None


class Service:
    """An app, its live state and a settable clock."""

    def __init__(self, reference: Reference | None = REFERENCE, now: float = NOW + 10) -> None:
        self.now = now
        self.reference = StubReference(reference)
        self.live = LiveStateHolder()
        self.app = create_app(SETTINGS)
        self.app.state.runtime = Runtime(live=self.live, reference=self.reference)
        self.app.state.clock = lambda: self.now
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def publish(self, feed_name: FeedName, entities: tuple[Any, ...], timestamp: int = NOW) -> None:
        reference = self.reference.current
        assert reference is not None
        message = feed(*entities, timestamp=timestamp)
        items: tuple[Any, ...]
        if feed_name is VP:
            items, stats = normalise_vehicles(message, reference, DEFAULT_THRESHOLDS)
        elif feed_name is TU:
            items, stats = normalise_trip_updates(message, reference, DEFAULT_THRESHOLDS)
        else:
            items, stats = normalise_alerts(message, reference)
        self.live.publish(
            FeedSnapshot(feed_name, timestamp, timestamp + 5, items, stats, reference.version_id)
        )

    def get(self, path: str, **headers: str) -> Any:
        return self.client.get(path, headers=headers)

    def data(self, path: str) -> Any:
        response = self.client.get(path)
        assert response.status_code == 200, response.text
        return response.json()["data"]


def service_with_network(now: float = NOW + 10) -> Service:
    service = Service(now=now)
    service.publish(VP, DEFAULT_VEHICLES)
    service.publish(TU, DEFAULT_TRIPS)
    service.publish(ALERTS, DEFAULT_ALERTS)
    return service
