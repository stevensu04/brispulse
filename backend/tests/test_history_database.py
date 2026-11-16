"""History code against PostgreSQL: the schedule lookup, the store and the recorder."""

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from brispulse.config import Settings
from brispulse.gtfs_static import service
from brispulse.history import store
from brispulse.history.accumulator import TripAccumulator, TripSummary
from brispulse.history.recorder import HistoryRecorder
from brispulse.history.schedule import (
    active_service_ids,
    scheduled_in_progress,
    scheduled_trips_per_route,
)
from brispulse.models import AlertRecord, FeedFetch, NetworkSample, RouteDayStats, TripRecord
from brispulse.realtime.collector import LiveStateHolder
from brispulse.realtime.model import FeedName
from brispulse.realtime.normalise import normalise_alerts
from brispulse.realtime.reference import Reference
from brispulse.realtime.thresholds import DEFAULT_THRESHOLDS as T
from tests.api_fixture import DEFAULT_ALERTS, DEFAULT_TRIPS, DEFAULT_VEHICLES
from tests.gtfs_fixture import write_zip
from tests.history_fixture import MONDAY, live_state, running
from tests.rt_fixture import NOW, REFERENCE, alert, feed, vehicle

pytestmark = pytest.mark.db

BRISBANE = ZoneInfo("Australia/Brisbane")
UTC = dt.UTC


def at(year: int, month: int, day: int, hour: int, minute: int) -> float:
    return dt.datetime(year, month, day, hour, minute, tzinfo=BRISBANE).timestamp()


@pytest.fixture
def version_id(settings: Settings, session_factory: sessionmaker[Session], tmp_path: Path) -> int:
    """The synthetic schedule: T1 08:00-08:11 and T2 23:50-24:30 on weekdays (bus R1),
    T3 09:00-09:25 on Saturdays (rail R2). On 25 December weekday service is removed
    and Saturday service added."""
    result = service.run_import(
        settings, session_factory, local_file=write_zip(tmp_path / "feed.zip")
    )
    assert result.version_id is not None
    return result.version_id


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


class TestSchedule:
    @pytest.mark.parametrize(
        ("moment", "expected"),
        [
            (at(2026, 11, 16, 8, 5), {"T1": "bus"}),
            (at(2026, 11, 16, 8, 0), {"T1": "bus"}),
            (at(2026, 11, 16, 8, 12), {}),
            (at(2026, 11, 16, 23, 55), {"T2": "bus"}),
            # 00:10 on Tuesday still belongs to Monday's service day (24:10).
            (at(2026, 11, 17, 0, 10), {"T2": "bus"}),
            (at(2026, 11, 17, 0, 31), {}),
            (at(2026, 11, 21, 9, 10), {"T3": "rail"}),
            # Saturday 00:10: Friday's late trip, not a Saturday one.
            (at(2026, 11, 21, 0, 10), {"T2": "bus"}),
            # Sunday 00:10: Saturday has no late trip.
            (at(2026, 11, 22, 0, 10), {}),
            (at(2026, 11, 22, 9, 10), {}),
        ],
    )
    def test_trips_in_progress(
        self,
        session_factory: sessionmaker[Session],
        version_id: int,
        moment: float,
        expected: dict[str, str],
    ) -> None:
        with session_factory() as session:
            assert scheduled_in_progress(session, version_id, moment, BRISBANE) == expected

    def test_calendar_exceptions_replace_the_weekly_pattern(
        self, session_factory: sessionmaker[Session], version_id: int
    ) -> None:
        christmas = dt.date(2026, 12, 25)  # a Friday
        with session_factory() as session:
            assert active_service_ids(session, version_id, christmas) == {"SATURDAY"}
            assert (
                scheduled_in_progress(session, version_id, at(2026, 12, 25, 8, 5), BRISBANE) == {}
            )
            assert scheduled_in_progress(
                session, version_id, at(2026, 12, 25, 9, 10), BRISBANE
            ) == {"T3": "rail"}

    def test_dates_outside_the_feed_have_no_service(
        self, session_factory: sessionmaker[Session], version_id: int
    ) -> None:
        with session_factory() as session:
            assert active_service_ids(session, version_id, dt.date(2027, 6, 7)) == set()
            assert scheduled_trips_per_route(session, version_id, dt.date(2027, 6, 7)) == {}

    def test_trips_per_route_for_a_service_day(
        self, session_factory: sessionmaker[Session], version_id: int
    ) -> None:
        with session_factory() as session:
            assert scheduled_trips_per_route(session, version_id, MONDAY) == {"R1": 2}
            assert scheduled_trips_per_route(session, version_id, dt.date(2026, 11, 21)) == {
                "R2": 1
            }


def summary(
    trip_id: str,
    median: int | None,
    *,
    obs: int = 5,
    route_id: str = "R1",
    mode: str = "bus",
    service_date: dt.date = MONDAY,
    completed: bool = True,
    samples: list[int] | None = None,
) -> TripSummary:
    moment = dt.datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
    return TripSummary(
        service_date=service_date,
        trip_id=trip_id,
        route_id=route_id,
        mode=mode,
        relationship="scheduled",
        vehicle_id="V1",
        static_version_id=7,
        first_obs_at=moment,
        last_obs_at=moment + dt.timedelta(minutes=obs),
        obs_count=obs,
        delay_median_s=median,
        delay_min_s=median,
        delay_max_s=median,
        delay_last_s=median,
        early_obs_count=0,
        late_obs_count=0,
        implausible_count=0,
        without_delay_count=0,
        completed=completed,
        samples=samples,
    )


class TestTripRecords:
    def test_a_summary_is_inserted_then_replaced(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory.begin() as session:
            store.upsert_trip_records(session, [summary("T1", 60, completed=False, samples=[60])])
        with session_factory.begin() as session:
            store.upsert_trip_records(session, [summary("T1", 90, obs=6, samples=None)])

        with session_factory() as session:
            record = session.scalars(select(TripRecord)).one()
            assert (record.delay_median_s, record.obs_count) == (90, 6)
            assert (record.completed, record.samples) == (True, None)

    def test_in_flight_trips_round_trip_exactly(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        in_flight = summary("T1", 60, completed=False, samples=[40, 60, 80])
        with session_factory.begin() as session:
            store.upsert_trip_records(session, [in_flight, summary("T2", 10)])

        with session_factory() as session:
            assert store.load_in_flight(session) == [in_flight]

    def test_many_summaries_are_written_in_batches(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        many = [summary(f"T{n}", n) for n in range(4_500)]
        with session_factory.begin() as session:
            store.upsert_trip_records(session, many)
            store.upsert_trip_records(session, [])

        with session_factory() as session:
            assert count(session, TripRecord) == 4_500


class TestAlertHistory:
    def test_unchanged_alerts_are_re_dated_and_changed_ones_versioned(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        first_seen = dt.datetime(2026, 11, 16, 9, 0, tzinfo=UTC)
        later = first_seen + dt.timedelta(minutes=5)
        original, _ = normalise_alerts(
            feed(alert("A1"), alert("A2", header="Night works")), REFERENCE
        )
        reworded, _ = normalise_alerts(
            feed(alert("A1"), alert("A2", header="Night works extended")), REFERENCE
        )

        with session_factory.begin() as session:
            store.upsert_alerts(session, original, first_seen)
        with session_factory.begin() as session:
            store.upsert_alerts(session, reworded, later)

        with session_factory() as session:
            records = session.scalars(select(AlertRecord).order_by(AlertRecord.first_seen_at)).all()
            seen = [(r.alert_id, r.header, r.first_seen_at, r.last_seen_at) for r in records]
        assert sorted(seen) == sorted(
            [
                ("A1", "Stop moved", first_seen, later),
                ("A2", "Night works", first_seen, first_seen),
                ("A2", "Night works extended", later, later),
            ]
        )

    def test_the_stored_content_is_complete(self, session_factory: sessionmaker[Session]) -> None:
        (item,), _ = normalise_alerts(feed(alert("A1", stop_ids=("S1",))), REFERENCE)
        with session_factory.begin() as session:
            store.upsert_alerts(session, [item], dt.datetime(2026, 11, 16, tzinfo=UTC))

        with session_factory() as session:
            record = session.scalars(select(AlertRecord)).one()
        assert (record.cause, record.effect) == ("construction", "stop_moved")
        assert record.description == "Use the temporary stop."
        assert record.active_periods == [[NOW - 3600, NOW + 3600]]
        assert (record.route_ids, record.stop_ids) == (["R1"], ["S1"])
        assert record.content_hash == store.alert_content_hash(item)


class TestRollup:
    def roll_up(self, session_factory: sessionmaker[Session], version_id: int | None = None) -> int:
        with session_factory.begin() as session:
            return store.roll_up_service_date(
                session,
                MONDAY,
                thresholds=T,
                static_version_id=version_id,
                computed_at=dt.datetime(2026, 11, 17, 8, 0, tzinfo=UTC),
            )

    def test_a_route_is_summarised_across_its_trips(
        self, session_factory: sessionmaker[Session], version_id: int
    ) -> None:
        medians = [-120, 0, 30, 118, 500, 900]
        with session_factory.begin() as session:
            store.upsert_trip_records(
                session, [summary(f"T{n}", median) for n, median in enumerate(medians)]
            )

        assert self.roll_up(session_factory, version_id) == 1

        with session_factory() as session:
            stats = session.scalars(select(RouteDayStats)).one()
        assert (stats.service_date, stats.route_id, stats.mode) == (MONDAY, "R1", "bus")
        assert stats.trips_observed == 6
        # The same nearest-rank rule as the live figures (see test_delay_stats).
        assert (stats.delay_p50_s, stats.delay_p90_s) == (30, 900)
        assert (stats.trips_early, stats.trips_within_band, stats.trips_late) == (1, 3, 2)
        assert stats.trips_scheduled == 2

    def test_trips_with_too_few_observations_are_left_out(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        records = [summary(f"T{n}", 60) for n in range(5)]
        records += [summary("SHORT", 2000, obs=2), summary("NODELAY", None, obs=0)]
        with session_factory.begin() as session:
            store.upsert_trip_records(session, records)

        self.roll_up(session_factory)

        with session_factory() as session:
            stats = session.scalars(select(RouteDayStats)).one()
        assert (stats.trips_observed, stats.trips_late, stats.delay_p90_s) == (5, 0, 60)

    def test_a_route_with_few_trips_gets_counts_but_no_percentiles(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory.begin() as session:
            store.upsert_trip_records(
                session,
                [summary(f"T{n}", 400, route_id="R2", mode="rail") for n in range(4)],
            )

        self.roll_up(session_factory)

        with session_factory() as session:
            stats = session.scalars(select(RouteDayStats)).one()
        assert (stats.trips_observed, stats.trips_late) == (4, 4)
        assert (stats.delay_p50_s, stats.delay_p90_s) == (None, None)
        # No schedule was consulted, so this is unknown rather than zero.
        assert stats.trips_scheduled is None

    def test_rolling_up_again_replaces_the_result(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory.begin() as session:
            store.upsert_trip_records(session, [summary(f"T{n}", 60) for n in range(5)])
        self.roll_up(session_factory)
        with session_factory.begin() as session:
            store.upsert_trip_records(session, [summary("LATE", 700)])

        self.roll_up(session_factory)

        with session_factory() as session:
            stats = session.scalars(select(RouteDayStats)).one()
        assert (stats.trips_observed, stats.trips_late) == (6, 1)

    def test_only_closed_days_without_a_rollup_are_due(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        sunday, tuesday = MONDAY - dt.timedelta(days=1), MONDAY + dt.timedelta(days=1)
        with session_factory.begin() as session:
            store.upsert_trip_records(
                session,
                [
                    summary(f"{day}-{n}", 60, service_date=day)
                    for day in (sunday, MONDAY, tuesday)
                    for n in range(5)
                ],
            )
            store.roll_up_service_date(
                session,
                sunday,
                thresholds=T,
                static_version_id=None,
                computed_at=dt.datetime.now(UTC),
            )

        def due(moment: float) -> list[dt.date]:
            with session_factory() as session:
                return store.service_dates_to_roll_up(session, moment, BRISBANE, T)

        # Monday's service day runs until 07:00 on Tuesday (31 hours after its midnight).
        assert due(at(2026, 11, 17, 6, 59)) == []
        assert due(at(2026, 11, 17, 7, 0)) == [MONDAY]
        assert due(at(2026, 11, 18, 7, 0)) == [MONDAY, tuesday]


class TestRetention:
    def test_old_rows_go_and_unrolled_days_are_kept(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        now = dt.datetime(2026, 12, 31, 12, 0, tzinfo=UTC)
        old_rolled, old_unrolled, recent = (
            dt.date(2026, 11, 1),
            dt.date(2026, 11, 2),
            dt.date(2026, 12, 20),
        )
        with session_factory.begin() as session:
            store.upsert_trip_records(
                session,
                [
                    summary(f"{day}-{n}", 60, service_date=day)
                    for day in (old_rolled, old_unrolled, recent)
                    for n in range(5)
                ],
            )
            for day in (old_rolled, recent):
                store.roll_up_service_date(
                    session, day, thresholds=T, static_version_id=None, computed_at=now
                )
            for days_ago in (31, 29):
                session.add(
                    FeedFetch(
                        feed="alerts",
                        fetched_at=now - dt.timedelta(days=days_ago),
                        duration_ms=1,
                        outcome="ok",
                    )
                )

        with session_factory.begin() as session:
            deleted = store.apply_retention(
                session, today=now.date(), now=now, fetch_days=30, trip_days=35
            )

        assert deleted == {"feed_fetch": 1, "trip_record": 5}
        with session_factory() as session:
            kept = set(session.scalars(select(TripRecord.service_date).distinct()))
            # The old day that was never rolled up keeps its rows: they are all there is.
            assert kept == {old_unrolled, recent}
            assert count(session, FeedFetch) == 1
            assert count(session, RouteDayStats) == 2


class FakeClock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def make_recorder(
    settings: Settings,
    session_factory: sessionmaker[Session],
    clock: FakeClock,
    reference: Reference = REFERENCE,
) -> tuple[HistoryRecorder, LiveStateHolder]:
    live = LiveStateHolder()
    recorder = HistoryRecorder(settings, session_factory, live, lambda: reference, clock=clock)
    return recorder, live


def publish_network(live: LiveStateHolder, timestamp: int) -> None:
    state = live_state(
        vehicles=DEFAULT_VEHICLES,
        trips=DEFAULT_TRIPS,
        alerts=DEFAULT_ALERTS,
        vehicles_at=timestamp,
        trips_at=timestamp,
        alerts_at=timestamp,
    )
    for snapshot in (state.vehicles, state.trip_updates, state.alerts):
        assert snapshot is not None
        live.publish(snapshot)


@pytest.mark.anyio
class TestRecorder:
    async def test_a_tick_writes_trips_a_sample_and_alerts(
        self, settings: Settings, session_factory: sessionmaker[Session]
    ) -> None:
        clock = FakeClock(NOW + 10)
        recorder, live = make_recorder(settings, session_factory, clock)
        publish_network(live, NOW)
        recorder.on_publish(FeedName.TRIP_UPDATES)
        clock.now = NOW + 130

        await recorder.tick()

        with session_factory() as session:
            trips = {t.trip_id: t for t in session.scalars(select(TripRecord))}
            samples = {s.mode: s for s in session.scalars(select(NetworkSample))}
            alerts = set(session.scalars(select(AlertRecord.alert_id)))
        # Only the two running trips are recorded, each with its predicted delay.
        assert {k: (t.delay_median_s, t.obs_count, t.completed) for k, t in trips.items()} == {
            "T1": (120, 1, False),
            "T2": (400, 1, False),
        }
        assert trips["T1"].service_date == MONDAY
        assert trips["T1"].samples == [120]
        assert set(samples) == {"all", "bus", "rail"}
        assert samples["all"].sampled_at == dt.datetime.fromtimestamp(NOW, UTC)
        assert (samples["all"].vehicles_fresh, samples["all"].trips_running) == (3, 2)
        assert samples["all"].alerts_active == 2
        assert alerts == {"A1", "A2", "A3"}
        assert [row.mode for row in recorder.latest_samples] == ["all", "bus", "rail"]

    async def test_coverage_uses_the_imported_schedule(
        self, settings: Settings, session_factory: sessionmaker[Session], version_id: int
    ) -> None:
        import dataclasses

        # 08:05 on Monday: the schedule has T1 in progress.
        moment = int(at(2026, 11, 16, 8, 5))
        clock = FakeClock(moment + 10)
        reference = dataclasses.replace(REFERENCE, version_id=version_id)
        recorder, live = make_recorder(settings, session_factory, clock, reference)
        state = live_state(
            vehicles=(vehicle("V1", trip_id="T1", timestamp=moment - 10),),
            trips=DEFAULT_TRIPS,
            vehicles_at=moment,
            trips_at=moment,
        )
        assert state.vehicles is not None and state.trip_updates is not None
        live.publish(state.vehicles)
        live.publish(state.trip_updates)

        await recorder.tick()

        sample = {row.mode: row for row in recorder.latest_samples}["all"]
        assert (sample.trips_scheduled, sample.trips_with_update, sample.trips_with_vehicle) == (
            1,
            1,
            1,
        )
        assert sample.static_version_id == version_id

    async def test_samples_sit_on_round_five_minute_marks(
        self, settings: Settings, session_factory: sessionmaker[Session]
    ) -> None:
        recorder, _ = make_recorder(settings, session_factory, FakeClock(NOW))

        assert recorder.sample_time(NOW + 299) == dt.datetime.fromtimestamp(NOW, UTC)
        assert recorder.sample_time(NOW + 300) == dt.datetime.fromtimestamp(NOW + 300, UTC)

    async def test_only_trip_updates_trigger_an_observation(
        self, settings: Settings, session_factory: sessionmaker[Session]
    ) -> None:
        recorder, live = make_recorder(settings, session_factory, FakeClock(NOW + 10))
        publish_network(live, NOW)

        recorder.on_publish(FeedName.VEHICLE_POSITIONS)
        recorder.on_publish(FeedName.ALERTS)
        assert len(recorder.accumulator) == 0

        recorder.on_publish(FeedName.TRIP_UPDATES)
        assert len(recorder.accumulator) == 2

    async def test_nothing_is_observed_from_data_too_old_to_record(
        self, settings: Settings, session_factory: sessionmaker[Session]
    ) -> None:
        recorder, live = make_recorder(settings, session_factory, FakeClock(NOW + 400))
        publish_network(live, NOW)

        recorder.on_publish(FeedName.TRIP_UPDATES)

        assert len(recorder.accumulator) == 0

    async def test_a_failed_write_is_retried_on_the_next_tick(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        recorder, live = make_recorder(settings, session_factory, FakeClock(NOW + 10))
        publish_network(live, NOW)
        recorder.on_publish(FeedName.TRIP_UPDATES)
        real_write = recorder._write

        def database_down(*args: object) -> None:
            raise ConnectionError("database is down")

        monkeypatch.setattr(recorder, "_write", database_down)
        await recorder.tick()
        with session_factory() as session:
            assert count(session, TripRecord) == 0
        assert recorder.latest_samples == ()

        monkeypatch.setattr(recorder, "_write", real_write)
        await recorder.tick()

        with session_factory() as session:
            assert count(session, TripRecord) == 2

    async def test_a_restart_resumes_in_flight_trips(
        self, settings: Settings, session_factory: sessionmaker[Session]
    ) -> None:
        clock = FakeClock(NOW + 10)
        first, live = make_recorder(settings, session_factory, clock)
        publish_network(live, NOW)
        first.on_publish(FeedName.TRIP_UPDATES)
        await first.flush()

        second, live = make_recorder(settings, session_factory, clock)
        assert second.restore() == 2
        clock.now = NOW + 70
        publish_network(live, NOW + 60)
        second.on_publish(FeedName.TRIP_UPDATES)
        await second.tick()

        with session_factory() as session:
            trip = session.get(TripRecord, (MONDAY, "T1"))
        assert trip is not None
        assert (trip.obs_count, trip.samples) == (2, [120, 120])
        assert trip.first_obs_at == dt.datetime.fromtimestamp(NOW, UTC)

    async def test_maintenance_rolls_up_closed_days(
        self, settings: Settings, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory.begin() as session:
            store.upsert_trip_records(session, [summary(f"T{n}", 60) for n in range(5)])
        clock = FakeClock(at(2026, 11, 17, 6, 0))
        recorder, _ = make_recorder(settings, session_factory, clock)

        recorder.maintain()
        with session_factory() as session:
            assert count(session, RouteDayStats) == 0

        clock.now = at(2026, 11, 17, 7, 30)
        recorder.maintain()
        recorder.maintain()

        with session_factory() as session:
            stats = session.scalars(select(RouteDayStats)).one()
        assert (stats.service_date, stats.trips_observed, stats.delay_p50_s) == (MONDAY, 5, 60)


def test_restored_accumulator_matches_what_was_stored(
    session_factory: sessionmaker[Session],
) -> None:
    accumulator = TripAccumulator(T)
    accumulator.observe([running("T1", 60), running("T2", 90, vehicle_id="V2")], NOW, 7)
    with session_factory.begin() as session:
        store.upsert_trip_records(session, accumulator.checkpoint())

    resumed = TripAccumulator(T)
    with session_factory() as session:
        resumed.restore(store.load_in_flight(session))

    assert len(resumed) == 2
