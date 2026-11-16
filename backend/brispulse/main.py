"""HTTP application.

The process also runs the collector (architecture §3.1). Because live state is held in
memory, the service must run as exactly one process: start it with a single worker.

Only the liveness probe is exposed so far; the ``/api/v1`` endpoints arrive in M2.4.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from brispulse import __version__
from brispulse.config import Settings, get_settings
from brispulse.logging_setup import configure_logging
from brispulse.runtime import running_service


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Settings are read here, not at import time, so importing this module never
        # requires a configured environment.
        active = settings or get_settings()
        configure_logging(active.log_level)
        if not active.collector_enabled:
            yield
            return
        async with running_service(active) as runtime:
            app.state.runtime = runtime
            yield

    app = FastAPI(title="BrisPulse", version=__version__, lifespan=lifespan)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        # Liveness only: says the process is up, nothing about data freshness.
        return {"status": "ok"}

    return app


app = create_app()
