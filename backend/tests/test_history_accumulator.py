import datetime as dt

from brispulse.history.accumulator import TripAccumulator
from brispulse.realtime.thresholds import DEFAULT_THRESHOLDS as T
from tests.history_fixture import MONDAY, running

T0 = 1_794_783_600  # any epoch second; observations are spaced from here
MINUTE = 60


def observe_series(
    accumulator: TripAccumulator, delays: list[int | None], trip_id: str = "T1"
) -> int:
    """One observation per minute. Returns the time of the last one."""
    when = T0
    for index, delay in enumerate(delays):
        when = T0 + index * MINUTE
        accumulator.observe([running(trip_id, delay)], when, static_version_id=7)
    return when


def test_a_trip_is_summarised_from_its_observations() -> None:
    accumulator = TripAccumulator(T)
    last = observe_series(accumulator, [-120, 0, 30, 118, 500, 900])

    (summary,) = accumulator.checkpoint()

    assert (summary.service_date, summary.trip_id) == (MONDAY, "T1")
    assert (summary.route_id, summary.mode, summary.vehicle_id) == ("R1", "bus", "V1")
    assert summary.static_version_id == 7
    assert summary.obs_count == 6
    assert (summary.delay_median_s, summary.delay_min_s, summary.delay_max_s) == (30, -120, 900)
    assert summary.delay_last_s == 900
    assert (summary.early_obs_count, summary.late_obs_count) == (1, 2)
    assert summary.first_obs_at == dt.datetime.fromtimestamp(T0, dt.UTC)
    assert summary.last_obs_at == dt.datetime.fromtimestamp(last, dt.UTC)
    assert summary.completed is False
    assert summary.samples == [-120, 0, 30, 118, 500, 900]


def test_the_same_data_seen_twice_counts_once() -> None:
    accumulator = TripAccumulator(T)
    accumulator.observe([running(delay=60)], T0, 7)
    accumulator.observe([running(delay=60)], T0, 7)
    accumulator.observe([running(delay=90)], T0 - 30, 7)

    (summary,) = accumulator.checkpoint()

    assert (summary.obs_count, summary.samples) == (1, [60])


def test_implausible_and_missing_delays_are_counted_apart() -> None:
    accumulator = TripAccumulator(T)
    accumulator.observe([running(delay=100)], T0, 7)
    accumulator.observe([running(delay=-6588, implausible=True)], T0 + 60, 7)
    accumulator.observe([running(delay=None)], T0 + 120, 7)

    (summary,) = accumulator.checkpoint()

    assert (summary.obs_count, summary.delay_median_s) == (1, 100)
    assert (summary.implausible_count, summary.without_delay_count) == (1, 1)


def test_a_trip_with_no_usable_delay_has_no_figures() -> None:
    accumulator = TripAccumulator(T)
    accumulator.observe([running(delay=None)], T0, 7)

    (summary,) = accumulator.checkpoint()

    assert summary.obs_count == 0
    assert (summary.delay_median_s, summary.delay_min_s, summary.delay_max_s) == (None, None, None)
    assert summary.delay_last_s is None


def test_an_unchanged_trip_is_not_written_again() -> None:
    accumulator = TripAccumulator(T)
    accumulator.observe([running(delay=60)], T0, 7)

    assert len(accumulator.checkpoint()) == 1
    assert accumulator.checkpoint() == []

    accumulator.observe([running(delay=80)], T0 + 60, 7)
    (summary,) = accumulator.checkpoint()
    assert summary.samples == [60, 80]


def test_a_trip_is_finished_once_newer_data_goes_ten_minutes_without_it() -> None:
    accumulator = TripAccumulator(T)
    accumulator.observe([running("T1", 60), running("T2", 10, vehicle_id="V2")], T0, 7)
    accumulator.checkpoint()

    # T2 keeps running; T1 is no longer among the running trips.
    accumulator.observe([running("T2", 20, vehicle_id="V2")], T0 + 600, 7)
    assert [s.trip_id for s in accumulator.checkpoint()] == ["T2"]
    assert len(accumulator) == 2

    accumulator.observe([running("T2", 30, vehicle_id="V2")], T0 + 601, 7)
    summaries = {s.trip_id: s for s in accumulator.checkpoint()}

    assert summaries["T1"].completed is True
    # A completed trip no longer carries its raw observations.
    assert summaries["T1"].samples is None
    assert (summaries["T1"].obs_count, summaries["T1"].delay_median_s) == (1, 60)
    assert summaries["T2"].completed is False
    assert len(accumulator) == 1


def test_nothing_is_finished_while_no_data_arrives() -> None:
    # Seen live: the collecting laptop slept for over an hour. Wall-clock time passing
    # without observations must not close trips that may still be running.
    accumulator = TripAccumulator(T)
    accumulator.observe([running(delay=60)], T0, 7)
    accumulator.checkpoint()

    assert accumulator.checkpoint() == []
    assert len(accumulator) == 1

    # Collection resumes 70 minutes later and the trip is still running: it continues.
    accumulator.observe([running(delay=200)], T0 + 70 * MINUTE, 7)
    (summary,) = accumulator.checkpoint()
    assert (summary.completed, summary.samples) == (False, [60, 200])


def test_the_same_trip_on_another_service_day_is_a_different_record() -> None:
    accumulator = TripAccumulator(T)
    tuesday = MONDAY + dt.timedelta(days=1)
    accumulator.observe([running(delay=60)], T0, 7)
    accumulator.observe([running(delay=90, service_date=tuesday)], T0 + 60, 7)

    summaries = accumulator.checkpoint()

    assert sorted((s.service_date, s.samples) for s in summaries) == [
        (MONDAY, [60]),
        (tuesday, [90]),
    ]


def test_restore_resumes_in_flight_trips_and_ignores_completed_ones() -> None:
    first = TripAccumulator(T)
    first.observe(
        [running("T1", 60), running("T2", -6588, implausible=True, vehicle_id="V2")], T0, 7
    )
    first.observe([running("T1", 80)], T0 + 60, 7)
    first.observe([running("T1", 80)], T0 + 700, 7)
    saved = first.checkpoint()
    assert {s.trip_id: s.completed for s in saved} == {"T1": False, "T2": True}

    second = TripAccumulator(T)
    second.restore(saved)

    assert len(second) == 1
    # Restored trips are already on disk, so they are not written again until they change.
    assert second.checkpoint() == []
    second.observe([running("T1", 120)], T0 + 760, 7)
    (summary,) = second.checkpoint()
    assert summary.samples == [60, 80, 80, 120]
    assert summary.first_obs_at == dt.datetime.fromtimestamp(T0, dt.UTC)


def test_the_latest_vehicle_and_relationship_are_kept() -> None:
    accumulator = TripAccumulator(T)
    accumulator.observe([running(delay=60, vehicle_id="V1")], T0, 7)
    accumulator.observe(
        [running(delay=60, vehicle_id="V9", relationship="replacement")], T0 + 60, 7
    )

    (summary,) = accumulator.checkpoint()

    assert (summary.vehicle_id, summary.relationship) == ("V9", "replacement")
