import pytest

from brispulse.delay_stats import nearest_rank, summarise_delays
from brispulse.realtime.model import TripState, Vehicle
from brispulse.realtime.populations import RunningTrip
from brispulse.realtime.thresholds import DEFAULT_THRESHOLDS as T


def running(delay: int | None, implausible: bool = False) -> RunningTrip:
    trip = TripState(
        trip_id="T",
        route_id="R1",
        mode="bus",
        start_date=None,
        start_time_s=None,
        relationship="scheduled",
        vehicle_id="V",
        timestamp=None,
        next_stop_delay_s=delay,
        delay_implausible=implausible,
        predictions=(),
        matched=True,
    )
    vehicle = Vehicle("V", None, "T", "R1", "bus", -27.5, 153.0, None, None, None, 0, 0, True, True)
    return RunningTrip(trip=trip, vehicle=vehicle)


@pytest.mark.parametrize(
    ("values", "fraction", "expected"),
    [
        ([10], 0.5, 10),
        ([10, 20], 0.5, 10),
        ([10, 20, 30], 0.5, 20),
        ([10, 20, 30, 40], 0.5, 20),
        (list(range(1, 11)), 0.9, 9),
        (list(range(1, 12)), 0.9, 10),
        ([10, 20, 30], 1.0, 30),
    ],
)
def test_nearest_rank_always_returns_an_observed_value(
    values: list[int], fraction: float, expected: int
) -> None:
    assert nearest_rank(values, fraction) == expected


def test_summary_of_a_typical_sample() -> None:
    summary = summarise_delays([running(d) for d in (-120, 0, 30, 118, 500, 900)], T)

    assert summary.sample_size == 6
    assert (summary.median_s, summary.p90_s) == (30, 900)
    assert (summary.early, summary.within_band, summary.late) == (1, 3, 2)
    assert (summary.excluded_implausible, summary.without_delay) == (0, 0)


def test_band_edges_belong_to_the_band() -> None:
    summary = summarise_delays([running(d) for d in (-61, -60, 300, 301)], T)

    assert (summary.early, summary.within_band, summary.late) == (1, 2, 1)


def test_implausible_and_missing_delays_are_left_out_and_counted() -> None:
    trips = [running(100), running(-6588, implausible=True), running(None), running(200)]

    summary = summarise_delays(trips, T)

    assert summary.sample_size == 2
    assert (summary.excluded_implausible, summary.without_delay) == (1, 1)
    assert summary.late == 0


def test_a_small_sample_gets_counts_but_no_percentiles() -> None:
    four = summarise_delays([running(d) for d in (10, 20, 30, 400)], T)
    five = summarise_delays([running(d) for d in (10, 20, 30, 400, 50)], T)

    assert (four.sample_size, four.median_s, four.p90_s) == (4, None, None)
    assert (four.within_band, four.late) == (3, 1)
    assert (five.median_s, five.p90_s) == (30, 400)


def test_no_running_trips_gives_an_empty_summary_not_an_error() -> None:
    summary = summarise_delays([], T)

    assert (summary.sample_size, summary.median_s, summary.p90_s) == (0, None, None)
    assert (summary.early, summary.within_band, summary.late) == (0, 0, 0)
