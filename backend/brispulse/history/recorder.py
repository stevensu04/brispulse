"""Turns the live state into stored history (architecture §4.3).

Three rhythms:

* on every new set of trip updates: one delay observation per running trip, in memory;
* every five minutes, on the clock: write trip summaries, a network sample and the
  alerts currently in the feed;
* hourly: roll up closed service days and delete rows past their retention.

In-memory work happens on the event loop thread, where the collector also runs, so the
two never race. Only database writes are moved to a worker thread.

A period when the service is down or the feeds are unusable leaves no rows. History has
gaps where collection had gaps; nothing is interpolated.
"""

import asyncio
import datetime as dt
import logging
import time
from collections.abc import Callable, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, sessionmaker

from brispulse.config import Settings
from brispulse.history import store
from brispulse.history.accumulator import TripAccumulator, TripSummary
from brispulse.history.sampling import (
    NetworkSampleRow,
    build_network_samples,
    recordable_running_trips,
)
from brispulse.history.schedule import scheduled_in_progress
from brispulse.realtime.collector import LiveStateHolder
from brispulse.realtime.model import FeedName, LiveState
from brispulse.realtime.reference import Reference
from brispulse.realtime.thresholds import DEFAULT_THRESHOLDS, Thresholds

logger = logging.getLogger(__name__)

# If the database stays unreachable, unwritten trip summaries are held for the next
# attempt, up to this many. Beyond it the oldest are dropped, and that is logged.
_MAX_UNWRITTEN = 50_000


class HistoryRecorder:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        live: LiveStateHolder,
        get_reference: Callable[[], Reference | None],
        *,
        thresholds: Thresholds = DEFAULT_THRESHOLDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._live = live
        self._get_reference = get_reference
        self._thresholds = thresholds
        self._clock = clock
        self._timezone = ZoneInfo(settings.service_timezone)
        self._interval = settings.history_sample_interval_seconds
        self.accumulator = TripAccumulator(thresholds)
        self._unwritten: dict[tuple[dt.date, str], TripSummary] = {}
        # The most recent network sample, for the API's coverage figures.
        self.latest_samples: Sequence[NetworkSampleRow] = ()

    # --- observation (event loop thread) -------------------------------------------

    def on_publish(self, feed: FeedName) -> None:
        """Called by the collector right after it publishes new data for ``feed``."""
        if feed is not FeedName.TRIP_UPDATES:
            return
        state = self._live.current
        trips = state.trip_updates
        if trips is None:
            return
        running = recordable_running_trips(state, self._clock(), self._timezone)
        if running is None:
            return
        self.accumulator.observe(running, trips.source_timestamp, trips.static_version_id)

    # --- the five-minute tick ------------------------------------------------------

    def sample_time(self, now: float) -> dt.datetime:
        """The start of the interval ``now`` falls in: samples sit on round clock times."""
        aligned = (int(now) // int(self._interval)) * int(self._interval)
        return dt.datetime.fromtimestamp(aligned, dt.UTC)

    async def tick(self) -> None:
        """Write what has accumulated, plus one network sample."""
        now = self._clock()
        state = self._live.current
        reference = self._get_reference()
        for summary in self.accumulator.checkpoint():
            self._unwritten[(summary.service_date, summary.trip_id)] = summary
        pending = list(self._unwritten.values())
        try:
            samples = await asyncio.to_thread(self._write, pending, state, reference, now)
        except Exception:
            logger.exception("could not write history; %d trip summaries held", len(pending))
            self._trim_unwritten()
            return
        for summary in pending:
            key = (summary.service_date, summary.trip_id)
            # Leave it if a newer summary for the same trip arrived meanwhile.
            if self._unwritten.get(key) is summary:
                del self._unwritten[key]
        self.latest_samples = samples

    def _trim_unwritten(self) -> None:
        excess = len(self._unwritten) - _MAX_UNWRITTEN
        if excess > 0:
            for key in list(self._unwritten)[:excess]:
                del self._unwritten[key]
            logger.error("dropped %d unwritten trip summaries: database unreachable", excess)

    def _write(
        self,
        summaries: Sequence[TripSummary],
        state: LiveState,
        reference: Reference | None,
        now: float,
    ) -> list[NetworkSampleRow]:
        """Blocking database work for one tick, in one transaction."""
        with self._session_factory.begin() as session:
            store.upsert_trip_records(session, summaries)
            scheduled = (
                scheduled_in_progress(session, reference.version_id, now, self._timezone)
                if reference is not None
                else None
            )
            samples = build_network_samples(
                state,
                scheduled,
                sampled_at=self.sample_time(now),
                now=now,
                timezone=self._timezone,
                thresholds=self._thresholds,
                static_version_id=reference.version_id if reference is not None else None,
            )
            store.write_network_samples(session, samples)
            if state.alerts is not None:
                store.upsert_alerts(
                    session, state.alerts.items, dt.datetime.fromtimestamp(now, dt.UTC)
                )
        return samples

    # --- start-up and maintenance (blocking) ---------------------------------------

    def restore(self) -> int:
        """Resume trips that were in flight when the service last stopped.

        However long ago that was: a trip that has since ended is closed as soon as ten
        minutes of new data have been observed without it.
        """
        with self._session_factory() as session:
            in_flight = store.load_in_flight(session)
        self.accumulator.restore(in_flight)
        if in_flight:
            logger.info("history: resumed %d in-flight trips", len(in_flight))
        return len(in_flight)

    def maintain(self) -> None:
        """Roll up closed service days, then delete rows past their retention."""
        now = self._clock()
        moment = dt.datetime.fromtimestamp(now, dt.UTC)
        reference = self._get_reference()
        with self._session_factory.begin() as session:
            for service_date in store.service_dates_to_roll_up(
                session, now, self._timezone, self._thresholds
            ):
                routes = store.roll_up_service_date(
                    session,
                    service_date,
                    thresholds=self._thresholds,
                    static_version_id=reference.version_id if reference is not None else None,
                    computed_at=moment,
                )
                logger.info("history: rolled up %s into %d routes", service_date, routes)
            deleted = store.apply_retention(
                session,
                today=dt.datetime.fromtimestamp(now, self._timezone).date(),
                now=moment,
                fetch_days=self._settings.feed_fetch_retention_days,
                trip_days=self._settings.trip_record_retention_days,
            )
        if any(deleted.values()):
            logger.info("history: retention deleted %s", deleted)

    # --- the loop -----------------------------------------------------------------

    async def run(self) -> None:
        try:
            await asyncio.to_thread(self.restore)
        except Exception:
            logger.exception("history: could not resume in-flight trips")
        last_maintenance = 0.0
        while True:
            now = self._clock()
            # Wake just after the next boundary, so the sample's label is in the past.
            await asyncio.sleep(self._interval - (now % self._interval) + 1.0)
            try:
                await self.tick()
                if self._clock() - last_maintenance >= self._settings.history_maintenance_seconds:
                    last_maintenance = self._clock()
                    await asyncio.to_thread(self.maintain)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("history: tick failed")

    async def flush(self) -> None:
        """Write in-flight trips before shutting down, so a restart can resume them."""
        try:
            await self.tick()
        except Exception:
            logger.exception("history: final write failed")
