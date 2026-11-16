"""HTTP application.

Only the liveness probe exists so far. The collector and the ``/api/v1`` endpoints
arrive in later M2 steps (architecture §14).
"""

from fastapi import FastAPI

from brispulse import __version__


def create_app() -> FastAPI:
    app = FastAPI(title="BrisPulse", version=__version__)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        # Liveness only: says the process is up, nothing about data freshness.
        return {"status": "ok"}

    return app


app = create_app()
