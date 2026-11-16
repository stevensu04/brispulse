import datetime as dt
from zoneinfo import ZoneInfo

from brispulse.history.sampling import build_network_samples, recordable_running_trips
from brispulse.realtime.model import LiveState
from brispulse.realtime.thresholds import DEFAULT_THRESHOLDS as T
from tests.api_fixture import DEFAULT_ALERTS, DEFAULT_TRIPS, DEFAULT_VEHICLES
from tests.history_fixture import live_state
from tests.rt_fixture import NOW

BRISBANE = ZoneInfo("Australia/Brisbane")
SAMPLED_AT = dt.datetime.fromtimestamp(NOW, dt.UTC)
# What the schedule says is in progress: T1 and T3 on the bus route, T2 on rail, and a
# ferry trip for which no real-time data exists at all.
SCHEDULED = {"T1": "bus", "T3": "bus", "T2": "rail", "T9": "ferry"}


def samples(state: LiveState, scheduled: dict[str, str] | None = SCHEDULED, now: float = NOW + 10):  # type: ignore[no-untyped-def]
    rows = build_network_samples(
        state,
        scheduled,
        sampled_at=SAMPLED_AT,
        now=now,
        timezone=BRISBANE,
        thresholds=T,
        static_version_id=7,
    )
    return {row.mode: row for row in rows}


def network() -> LiveState:
    return live_state(vehicles=DEFAULT_VEHICLES, trips=DEFAULT_TRIPS, alerts=DEFAULT_ALERTS)


def test_one_row_for_the_network_and_one_per_mode() -> None:
    rows = samples(network())

    assert list(rows) == ["all", "bus", "ferry", "rail"]
    assert all(row.sampled_at == SAMPLED_AT and row.static_version_id == 7 for row in rows.values())
    assert {row.vehicle_positions_state for row in rows.values()} == {"live"}


def test_vehicle_and_running_trip_counts() -> None:
    rows = samples(network())

    assert (rows["all"].vehicles_fresh, rows["all"].vehicles_last_seen) == (3, 1)
    assert (rows["bus"].vehicles_fresh, rows["bus"].vehicles_last_seen) == (2, 1)
    assert (rows["rail"].vehicles_fresh, rows["rail"].vehicles_last_seen) == (1, 0)
    assert (rows["all"].trips_running, rows["bus"].trips_running, rows["rail"].trips_running) == (
        2,
        1,
        1,
    )
    # A mode with no live data at all still gets a row: real zeros, from live feeds.
    assert (rows["ferry"].vehicles_fresh, rows["ferry"].trips_running) == (0, 0)


def test_delay_figures_follow_the_small_sample_rule() -> None:
    row = samples(network())["all"]

    assert (row.delay_sample_size, row.delay_median_s, row.delay_p90_s) == (2, None, None)
    assert (row.delay_early, row.delay_within_band, row.delay_late) == (0, 1, 1)
    assert row.delay_excluded_implausible == 0


def test_coverage_compares_the_schedule_with_live_data() -> None:
    rows = samples(network())

    # T1, T2, T3 have trip updates; T9 has none. T3's vehicle is stale.
    assert (rows["all"].trips_scheduled, rows["all"].trips_with_update) == (4, 3)
    assert rows["all"].trips_with_vehicle == 2
    assert (rows["bus"].trips_scheduled, rows["bus"].trips_with_update) == (2, 2)
    assert rows["bus"].trips_with_vehicle == 1
    assert (rows["ferry"].trips_scheduled, rows["ferry"].trips_with_update) == (1, 0)
    assert rows["ferry"].trips_with_vehicle == 0


def test_alert_counts_sit_on_the_network_row_only() -> None:
    rows = samples(network())

    assert (rows["all"].alerts_active, rows["all"].alerts_active_planned_works) == (2, 1)
    assert (rows["bus"].alerts_active, rows["rail"].alerts_active) == (None, None)


def test_without_a_schedule_coverage_is_empty_not_zero() -> None:
    rows = samples(network(), scheduled=None)

    assert list(rows) == ["all", "bus", "rail"]
    assert rows["all"].trips_scheduled is None
    assert rows["all"].trips_with_update is None
    assert rows["all"].vehicles_fresh == 3


def test_stale_vehicle_data_is_not_recorded_as_history() -> None:
    # Vehicles last updated 400 s ago: still shown to users as stale, but not history.
    state = live_state(
        vehicles=DEFAULT_VEHICLES,
        trips=DEFAULT_TRIPS,
        alerts=DEFAULT_ALERTS,
        vehicles_at=NOW - 400,
    )

    rows = samples(state)

    row = rows["all"]
    assert (row.vehicle_positions_state, row.trip_updates_state) == ("stale", "live")
    assert (row.vehicles_fresh, row.vehicles_last_seen) == (None, None)
    assert (row.trips_running, row.delay_sample_size, row.delay_late) == (None, None, None)
    # Trip updates are live, so that half of coverage is still known.
    assert (row.trips_scheduled, row.trips_with_update, row.trips_with_vehicle) == (4, 3, None)
    assert row.alerts_active == 2
    assert recordable_running_trips(state, NOW + 10, BRISBANE) is None


def test_delayed_data_is_still_recorded() -> None:
    rows = samples(network(), now=NOW + 200)

    assert rows["all"].vehicle_positions_state == "delayed"
    assert rows["all"].vehicles_fresh == 3
    assert rows["all"].trips_running == 2


def test_nothing_fetched_yields_a_row_that_says_so() -> None:
    rows = samples(LiveState(), scheduled=None)

    assert list(rows) == ["all"]
    row = rows["all"]
    assert (row.vehicle_positions_state, row.trip_updates_state, row.alerts_state) == (
        "unavailable",
        "unavailable",
        "unavailable",
    )
    assert (row.vehicles_fresh, row.trips_running, row.alerts_active) == (None, None, None)
