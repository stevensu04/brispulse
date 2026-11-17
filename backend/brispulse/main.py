"""HTTP application.

The process also runs the collector (architecture §3.1). Because live state is held in
memory, the service must run as exactly one process: start it with a single worker.
"""

import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware
from starlette.staticfiles import StaticFiles

from brispulse import __version__
from brispulse.api.errors import install_error_handlers
from brispulse.api.router import router as api_router
from brispulse.config import Settings, get_settings
from brispulse.logging_setup import configure_logging
from brispulse.runtime import running_service

DESCRIPTION = """
Read-only API for BrisPulse: live public transport conditions in South East Queensland.

Every response has the same envelope: `data`, and `meta` describing how fresh the
underlying feeds are. A value that cannot be given is `null`, never `0`; `meta.notes`
says why.

Contains Translink data © State of Queensland (Department of Transport and Main Roads),
licensed under CC BY 4.0. BrisPulse is independent and not endorsed by Translink.
"""


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

    app = FastAPI(
        title="BrisPulse", version=__version__, description=DESCRIPTION, lifespan=lifespan
    )
    app.state.settings = settings
    app.state.clock = time.time
    # The vehicle list was 695 kB of JSON in the evening peak and 98 kB compressed
    # (measured 2026-11-16).
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    install_error_handlers(app)
    app.include_router(api_router)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        # Liveness only: says the process is up, nothing about data freshness.
        return {"status": "ok"}

    # Mounted last, so it only receives what no route above claimed. An unknown
    # /api path still gets the API's JSON error, not the web app.
    web_dir = (settings.web_dir if settings is not None else None) or os.environ.get(
        "BRISPULSE_WEB_DIR"
    )
    if web_dir and Path(web_dir).is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app


app = create_app()
