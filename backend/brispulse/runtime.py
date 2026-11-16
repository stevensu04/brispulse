"""Background work the service does while it runs (architecture §3).

Three long-lived tasks share one process with the HTTP application:

* the collector polls the real-time feeds;
* the static refresher periodically imports a new schedule, in a subprocess;
* the reference refresher reloads in-memory lookups when the active version changes.

Each loop catches its own failures and tries again later. None of them can take the
HTTP application down.
"""

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

import httpx2
from sqlalchemy.orm import Session, sessionmaker

from brispulse.config import Settings
from brispulse.db import make_engine, make_session_factory
from brispulse.realtime.collector import Collector, LiveStateHolder
from brispulse.realtime.fetch_log import make_fetch_recorder
from brispulse.realtime.reference import Reference, active_version_id, load_reference

logger = logging.getLogger(__name__)

# How often to look for a newly activated static version. The check is one small query.
_REFERENCE_CHECK_SECONDS = 300.0
# Until a first version has loaded, look more often: the service is useless without one.
_REFERENCE_RETRY_SECONDS = 30.0


class ReferenceHolder:
    """The static lookups currently in use. None until a version has been imported."""

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


@dataclass(frozen=True, slots=True)
class Runtime:
    """What the HTTP layer needs from the running service."""

    live: LiveStateHolder
    reference: HoldsReference


async def keep_reference_current(holder: ReferenceHolder) -> None:
    while True:
        try:
            await asyncio.to_thread(holder.refresh)
        except Exception:
            logger.exception("could not refresh the static reference")
        waiting = holder.current is None
        await asyncio.sleep(_REFERENCE_RETRY_SECONDS if waiting else _REFERENCE_CHECK_SECONDS)


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


@asynccontextmanager
async def running_service(settings: Settings) -> AsyncIterator[Runtime]:
    """Start the background tasks and stop them cleanly on exit."""
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    reference = ReferenceHolder(session_factory)
    live = LiveStateHolder()
    client = httpx2.AsyncClient(
        headers={"User-Agent": settings.user_agent},
        timeout=settings.realtime_timeout_seconds,
        follow_redirects=True,
    )
    collector = Collector(
        settings,
        client,
        live,
        lambda: reference.current,
        make_fetch_recorder(session_factory),
    )
    # Load the reference before the first poll. Otherwise every feed's first poll finds
    # nothing to validate against and waits a full interval before trying again.
    try:
        await asyncio.to_thread(reference.refresh)
    except Exception:
        logger.exception("could not load the static reference at start-up")
    tasks = [
        asyncio.create_task(keep_static_current(settings, reference), name="static-refresh"),
        asyncio.create_task(keep_reference_current(reference), name="reference-refresh"),
        asyncio.create_task(collector.run(), name="collector"),
    ]
    try:
        yield Runtime(live=live, reference=reference)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await client.aclose()
        engine.dispose()
