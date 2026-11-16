"""Real-time coverage in the overview comes from the latest stored network sample."""

import datetime as dt
from dataclasses import dataclass, field

from brispulse.history.sampling import NetworkSampleRow
from brispulse.runtime import Runtime
from tests.api_fixture import Service, service_with_network
from tests.rt_fixture import NOW


@dataclass
class StubHistory:
    latest_samples: list[NetworkSampleRow] = field(default_factory=list)


def sample(
    mode: str, scheduled: int | None, updates: int | None, vehicles: int | None, at: int = NOW
) -> NetworkSampleRow:
    return NetworkSampleRow(
        sampled_at=dt.datetime.fromtimestamp(at, dt.UTC),
        mode=mode,
        static_version_id=7,
        vehicle_positions_state="live",
        trip_updates_state="live",
        alerts_state="live",
        trips_scheduled=scheduled,
        trips_with_update=updates,
        trips_with_vehicle=vehicles,
    )


def with_history(service: Service, rows: list[NetworkSampleRow]) -> Service:
    runtime = service.app.state.runtime
    service.app.state.runtime = Runtime(
        live=runtime.live,
        reference=runtime.reference,
        history=StubHistory(rows),  # type: ignore[arg-type]
    )
    return service


def test_coverage_is_reported_overall_and_by_mode() -> None:
    rows = [
        sample("all", 1243, 1153, 1137),
        sample("bus", 1138, 1049, 1033),
        sample("rail", 70, 70, 70),
    ]
    service = with_history(service_with_network(now=NOW + 200), rows)

    coverage = service.data("/api/v1/overview")["coverage"]

    assert coverage == {
        "trips_scheduled": 1243,
        "trips_with_update": 1153,
        "trips_with_vehicle": 1137,
        "sampled_at": "2026-11-16T09:00:00+10:00",
        "by_mode": {
            "bus": {"trips_scheduled": 1138, "trips_with_update": 1049, "trips_with_vehicle": 1033},
            "rail": {"trips_scheduled": 70, "trips_with_update": 70, "trips_with_vehicle": 70},
        },
    }


def test_without_history_coverage_is_null_with_a_note() -> None:
    body = service_with_network().get("/api/v1/overview").json()

    assert body["data"]["coverage"] is None
    assert "coverage: not computed yet; it is sampled every few minutes." in body["meta"]["notes"]


def test_an_old_sample_is_withheld() -> None:
    service = with_history(service_with_network(now=NOW + 601), [sample("all", 100, 90, 80)])

    body = service.get("/api/v1/overview").json()

    assert body["data"]["coverage"] is None
    assert "coverage: the latest sample is 601 s old and is withheld." in body["meta"]["notes"]


def test_a_sample_taken_without_the_schedule_gives_no_coverage() -> None:
    service = with_history(service_with_network(), [sample("all", None, None, None)])

    body = service.get("/api/v1/overview").json()

    assert body["data"]["coverage"] is None
    assert any("schedule could not be consulted" in note for note in body["meta"]["notes"])


def test_half_known_coverage_keeps_the_unknown_half_null() -> None:
    # Vehicle positions were stale when the sample was taken.
    service = with_history(service_with_network(), [sample("all", 100, 93, None)])

    coverage = service.data("/api/v1/overview")["coverage"]

    assert (coverage["trips_with_update"], coverage["trips_with_vehicle"]) == (93, None)
