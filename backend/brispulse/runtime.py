"""Background work the service does while it runs (architecture §3 and §19).

The service runs in one of two shapes, chosen by whether a database is configured.

**Live-only** (no database): the schedule is read straight from TransLink at start-up
and held in memory; the collector polls the real-time feeds; nothing is stored. This
fits a host that stops the service when nobody is using it: on waking, it is showing
live data again within seconds, and there is nothing to lose when it stops.

**With a database**: the schedule is imported into PostgreSQL in a subprocess, every
fetch is logged, and history is recorded. This needs a host that never sleeps.

Each background loop catches its own failures and tries again later. None of them can
take the HTTP application down.
"""

import asyncio
import logging
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

import httpx2
from sqlalchemy.orm import Session, sessionmaker

from brispulse.config import Settings
from brispulse.db import make_engine, make_session_factory
from brispulse.history.recorder import HistoryRecorder
from brispulse.realtime.collector import Collector, FetchRecord, LiveStateHolder
from brispulse.realtime.fetch_log import make_fetch_recorder
from brispulse.realtime.reference import Reference, active_version_id, load_reference
from brispulse.realtime.zip_reference import ZipReferenceHolder

logger = logging.getLogger(__name__)

# How often to look for a newly activated static version. The check is one small query.
_REFERENCE_CHECK_SECONDS = 300.0
# Until a first version has loaded, look more often: the service is useless without one.
_REFERENCE_RETRY_SECONDS = 30.0


class ReferenceHolder:
    """The static lookups currently in use, loaded from the database."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self.current: Reference | None = None

    def refresh(self) -> bool:
        """Load the active version if it differs from the one held. Blocking."""
        with self._session_factory() as session:
            version_id = active_version_id(session)
            if version_id is None:
                return False
            if self.current is not None and self.current.version_id == version_id:
                return False
            self.current = load_reference(session)
        logger.info("loaded static reference version %s", version_id)
        return True


class HoldsReference(Protocol):
    """Anything that can say which static reference is current."""

    @property
    def current(self) -> Reference | None: ...


class RefreshesReference(HoldsReference, Protocol):
    def refresh(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class Runtime:
    """What the HTTP layer needs from the running service."""

    live: LiveStateHolder
    reference: HoldsReference
    # None when no history is kept: in live-only mode, or when it is turned off.
    history: HistoryRecorder | None = None


async def keep_reference_current(holder: RefreshesReference, check_seconds: float) -> None:
    """Load the reference, then look for a newer one every ``check_seconds``."""
    while True:
        try:
            await asyncio.to_thread(holder.refresh)
        except Exception:
            logger.exception("could not refresh the static reference")
        waiting = holder.current is None
        await asyncio.sleep(_REFERENCE_RETRY_SECONDS if waiting else check_seconds)


async def import_static_feed() -> int:
    """Run the static importer as a subprocess and return its exit code.

    A subprocess keeps the import's CPU and memory (about 240 MB at peak, measured
    2026-11-16) out of the process that serves requests.
    """
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "brispulse.gtfs_static", "import"
    )
    return await process.wait()


async def keep_static_current(settings: Settings, holder: ReferenceHolder) -> None:
    while True:
        try:
            exit_code = await import_static_feed()
            if exit_code != 0:
                logger.error("static import exited with code %s", exit_code)
            await asyncio.to_thread(holder.refresh)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("static refresh failed")
        await asyncio.sleep(settings.static_check_interval_seconds)


def _discard_fetch_record(record: FetchRecord) -> None:
    """Live-only mode keeps no fetch log. The collector still logs every failure."""


def _make_client(settings: Settings) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        headers={"User-Agent": settings.user_agent},
        timeout=settings.realtime_timeout_seconds,
        follow_redirects=True,
    )


async def _stop(tasks: list[asyncio.Task[None]]) -> None:
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


@asynccontextmanager
async def _live_only_service(settings: Settings) -> AsyncIterator[Runtime]:
    reference = ZipReferenceHolder(settings)
    live = LiveStateHolder()
    client = _make_client(settings)
    collector = Collector(settings, client, live, lambda: reference.current, _discard_fetch_record)
    # The schedule download is not awaited here: the HTTP application starts at once
    # and reports that it is still loading, instead of making a waking host time out.
    tasks = [
        asyncio.create_task(
            keep_reference_current(reference, settings.static_check_interval_seconds),
            name="reference-refresh",
        ),
        asyncio.create_task(collector.run(), name="collector"),
    ]
    logger.info("running live-only: no database, no history")
    try:
        yield Runtime(live=live, reference=reference)
    finally:
        await _stop(tasks)
        await client.aclose()


@asynccontextmanager
async def _database_service(settings: Settings, database_url: str) -> AsyncIterator[Runtime]:
    engine = make_engine(database_url)
    session_factory = make_session_factory(engine)
    reference = ReferenceHolder(session_factory)
    live = LiveStateHolder()
    client = _make_client(settings)
    history = (
        HistoryRecorder(settings, session_factory, live, lambda: reference.current)
        if settings.history_enabled
        else None
    )
    on_publish: Callable[..., None] | None = history.on_publish if history is not None else None
    collector = Collector(
        settings,
        client,
        live,
        lambda: reference.current,
        make_fetch_recorder(session_factory),
        on_publish=on_publish,
    )
    # Load the reference before the first poll: it is one quick query, and the first
    # poll then has something to validate against.
    try:
        await asyncio.to_thread(reference.refresh)
    except Exception:
        logger.exception("could not load the static reference at start-up")
    tasks = [
        asyncio.create_task(keep_static_current(settings, reference), name="static-refresh"),
        asyncio.create_task(
            keep_reference_current(reference, _REFERENCE_CHECK_SECONDS), name="reference-refresh"
        ),
        asyncio.create_task(collector.run(), name="collector"),
    ]
    if history is not None:
        tasks.append(asyncio.create_task(history.run(), name="history"))
    try:
        yield Runtime(live=live, reference=reference, history=history)
    finally:
        await _stop(tasks)
        if history is not None:
            # After the tasks have stopped, so nothing else is writing.
            await history.flush()
        await client.aclose()
        engine.dispose()


@asynccontextmanager
async def running_service(settings: Settings) -> AsyncIterator[Runtime]:
    """Start the background tasks and stop them cleanly on exit."""
    if settings.database_url is None:
        async with _live_only_service(settings) as runtime:
            yield runtime
    else:
        async with _database_service(settings, settings.database_url) as runtime:
            yield runtime
