"""Per-trip delay observations, gathered in memory while a trip runs (architecture §4.3).

Every time new trip updates arrive, each running trip contributes one observation: its
predicted delay at the next stop. When a trip stops appearing among the running trips
it is finished, and its observations are reduced to one summary row.

Nothing here touches the database. ``TripSummary`` rows are handed to the store.
"""

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, field

from brispulse.delay_stats import nearest_rank
from brispulse.realtime.populations import RunningTrip
from brispulse.realtime.thresholds import Thresholds


@dataclass(frozen=True, slots=True)
class TripSummary:
    """What is stored for one trip on one service day."""

    service_date: dt.date
    trip_id: str
    route_id: str | None
    mode: str | None
    relationship: str
    vehicle_id: str | None
    static_version_id: int
    first_obs_at: dt.datetime
    last_obs_at: dt.datetime
    obs_count: int
    delay_median_s: int | None
    delay_min_s: int | None
    delay_max_s: int | None
    delay_last_s: int | None
    early_obs_count: int
    late_obs_count: int
    implausible_count: int
    without_delay_count: int
    completed: bool
    # Raw delays in observation order; None once the trip is complete.
    samples: list[int] | None


@dataclass(slots=True)
class _Flight:
    """A trip that is being observed."""

    service_date: dt.date
    trip_id: str
    route_id: str | None
    mode: str | None
    relationship: str
    vehicle_id: str | None
    static_version_id: int
    first_obs_at: int
    last_obs_at: int
    samples: list[int] = field(default_factory=list)
    implausible: int = 0
    without_delay: int = 0
    # Changed since it was last written to the database.
    dirty: bool = True


def _utc(epoch: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(epoch, dt.UTC)


class TripAccumulator:
    def __init__(self, thresholds: Thresholds) -> None:
        self._thresholds = thresholds
        self._flights: dict[tuple[dt.date, str], _Flight] = {}
        # Timestamp of the newest data observed so far.
        self._latest_as_of = 0

    def __len__(self) -> int:
        return len(self._flights)

    def observe(self, running: Iterable[RunningTrip], as_of: int, static_version_id: int) -> None:
        """Record one observation per running trip, taken from data produced at ``as_of``."""
        self._latest_as_of = max(self._latest_as_of, as_of)
        for item in running:
            trip = item.trip
            if trip.start_date is None:
                continue  # cannot happen for a running trip; keeps the key well-typed
            key = (trip.start_date, trip.trip_id)
            flight = self._flights.get(key)
            if flight is None:
                flight = _Flight(
                    service_date=trip.start_date,
                    trip_id=trip.trip_id,
                    route_id=trip.route_id,
                    mode=trip.mode,
                    relationship=trip.relationship,
                    vehicle_id=item.vehicle.vehicle_id,
                    static_version_id=static_version_id,
                    first_obs_at=as_of,
                    last_obs_at=as_of,
                )
                self._flights[key] = flight
            elif as_of <= flight.last_obs_at:
                # The same data seen twice must not count twice.
                continue

            flight.last_obs_at = as_of
            flight.relationship = trip.relationship
            flight.vehicle_id = item.vehicle.vehicle_id
            flight.dirty = True
            if trip.next_stop_delay_s is None:
                flight.without_delay += 1
            elif trip.delay_implausible:
                flight.implausible += 1
            else:
                flight.samples.append(trip.next_stop_delay_s)

    def _summarise(self, flight: _Flight, *, completed: bool) -> TripSummary:
        samples = flight.samples
        ordered = sorted(samples)
        thresholds = self._thresholds
        return TripSummary(
            service_date=flight.service_date,
            trip_id=flight.trip_id,
            route_id=flight.route_id,
            mode=flight.mode,
            relationship=flight.relationship,
            vehicle_id=flight.vehicle_id,
            static_version_id=flight.static_version_id,
            first_obs_at=_utc(flight.first_obs_at),
            last_obs_at=_utc(flight.last_obs_at),
            obs_count=len(samples),
            # Even one observation has a median; whether a trip has enough observations
            # to enter route statistics is decided when those are computed.
            delay_median_s=nearest_rank(ordered, 0.5) if ordered else None,
            delay_min_s=ordered[0] if ordered else None,
            delay_max_s=ordered[-1] if ordered else None,
            delay_last_s=samples[-1] if samples else None,
            early_obs_count=sum(1 for d in samples if d < -thresholds.delay_early_s),
            late_obs_count=sum(1 for d in samples if d > thresholds.delay_late_s),
            implausible_count=flight.implausible,
            without_delay_count=flight.without_delay,
            completed=completed,
            samples=None if completed else list(samples),
        )

    def checkpoint(self) -> list[TripSummary]:
        """Summaries to write now: finished trips, and running trips that have changed.

        A trip is finished once newer data has been observed for
        ``trip_finished_after_s`` without it. The comparison is against the latest
        observed data, not the wall clock: while collection is interrupted nothing is
        observed, so nothing is declared finished, and a trip still running when
        collection resumes simply continues.

        Finished trips are returned as complete and forgotten. Known limit: a trip whose
        vehicle stops reporting for longer than that and then reappears starts again,
        and its second summary replaces the first.
        """
        cutoff = self._latest_as_of - self._thresholds.trip_finished_after_s
        summaries: list[TripSummary] = []
        for key, flight in list(self._flights.items()):
            if flight.last_obs_at < cutoff:
                summaries.append(self._summarise(flight, completed=True))
                del self._flights[key]
            elif flight.dirty:
                summaries.append(self._summarise(flight, completed=False))
                flight.dirty = False
        return summaries

    def restore(self, summaries: Iterable[TripSummary]) -> None:
        """Resume in-flight trips from their last checkpoint, after a restart."""
        for summary in summaries:
            if summary.completed or summary.samples is None:
                continue
            self._flights[(summary.service_date, summary.trip_id)] = _Flight(
                service_date=summary.service_date,
                trip_id=summary.trip_id,
                route_id=summary.route_id,
                mode=summary.mode,
                relationship=summary.relationship,
                vehicle_id=summary.vehicle_id,
                static_version_id=summary.static_version_id,
                first_obs_at=int(summary.first_obs_at.timestamp()),
                last_obs_at=int(summary.last_obs_at.timestamp()),
                samples=list(summary.samples),
                implausible=summary.implausible_count,
                without_delay=summary.without_delay_count,
                dirty=False,
            )
