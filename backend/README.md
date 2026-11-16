# BrisPulse backend

Python service: collects TransLink data, stores history in PostgreSQL and serves the JSON API.
Design: [`../BRISPULSE-ARCHITECTURE.md`](../BRISPULSE-ARCHITECTURE.md).

## Layout

```
brispulse/              the Python package
  config.py             settings from environment variables
  db.py, models.py      database engine and tables
  main.py               HTTP application
  gtfs_static/          import of TransLink's static GTFS schedule
  realtime/             collector: fetch, decode, validate, freshness, running trips
  api/                  the /api/v1 endpoints: schemas, data builders, routing, errors
  delay_stats.py        delay summaries (median, 90th percentile, bands)
  history/              stored history: trip summaries, 5-minute samples, alerts, daily rollup
  runtime.py            background tasks that run alongside the HTTP application
migrations/             Alembic database migrations
tests/                  pytest suite
```

The package sits directly in `backend/` rather than under `src/`, so it is importable from
this directory without depending on an editable install. This is deliberate: Python on macOS
ignores the editable-install `.pth` file when the project lives in a cloud-synced folder
(the file gets the hidden flag), which makes `import brispulse` fail in a way that is hard
to diagnose.

## Requirements

- [uv](https://docs.astral.sh/uv/) (installs the right Python and dependencies)
- Docker (for the local PostgreSQL database)

## Local setup

Run from the repository root:

```bash
cp .env.example .env
docker compose up -d db
```

Then from `backend/`:

```bash
uv sync
uv run alembic upgrade head
uv run python -m brispulse.gtfs_static import
uv run uvicorn brispulse.main:app
```

Starting the service starts the collector: it polls TransLink's real-time feeds (vehicle
positions every 30 s, trip updates every 60 s, alerts every 120 s by default), checks for
a new static schedule every 6 hours, and writes one row per fetch to the `feed_fetch`
table. Set `BRISPULSE_COLLECTOR_ENABLED=false` to run the HTTP application without
contacting TransLink.

It also records history: one delay observation per running trip whenever new trip updates
arrive, a network sample every five minutes (including real-time coverage), the alerts in
the feed, and once a service day has closed, a per-route rollup. Set
`BRISPULSE_HISTORY_ENABLED=false` to collect without storing any of this.

| Table | Holds | Kept for |
| --- | --- | --- |
| `feed_fetch` | One row per fetch attempt | 30 days |
| `trip_record` | One row per trip per service day: its delay summary | 35 days, and only deleted once rolled up |
| `network_sample` | Network state every five minutes, per mode | Indefinitely |
| `alert_record` | Each alert's content and when it was seen | Indefinitely |
| `route_day_stats` | Per-route daily rollup | Indefinitely |

History has gaps wherever collection had gaps. Nothing is interpolated or back-filled.

**Run exactly one process.** Live state is held in memory, so do not start uvicorn with
several workers, and avoid `--reload` while collecting (each reload starts over).

## API

With the service running, interactive documentation is at `http://127.0.0.1:8000/docs`
and the OpenAPI document at `/openapi.json`.

| Endpoint | Returns |
| --- | --- |
| `GET /api/v1/status` | State of each feed, last fetch attempts, schedule in use |
| `GET /api/v1/overview` | Fresh vehicles, running trips, predicted-delay summary, alert counts |
| `GET /api/v1/vehicles` | Vehicle positions; filters `mode`, `route_id`, `bbox`, `fresh_only` |
| `GET /api/v1/routes` | Every route with live counts; filter `mode` |
| `GET /api/v1/routes/{route_id}` | One route: vehicles, running trips, alerts |
| `GET /api/v1/trips/{trip_id}` | One trip: predicted times and delays at upcoming stops |
| `GET /api/v1/alerts` | Service alerts; filters `active`, `route_id`, `stop_id` |
| `GET /api/v1/meta/metrics` | Metric definitions, thresholds, attribution |
| `GET /healthz` | Process liveness only |

Every response is `{"data": ..., "meta": ...}`. `meta.feeds` gives each feed's state
(`live`, `delayed`, `stale`, `unavailable`) and timestamps. **A value that cannot be
given is `null`, never `0` or an empty list**, and `meta.notes` says why. Errors are
`{"error": {"code": ..., "message": ...}}`.

These endpoints read only from memory, so they keep answering if the database is down.
Only `GET` is supported.

## Checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

Tests marked `db` need the local database to be running. They create and use a separate
`brispulse_test` database and never touch `brispulse`. Without a database they are skipped
locally and fail in CI. Warnings are treated as errors.

## Commands

| Command | Purpose |
| --- | --- |
| `python -m brispulse.gtfs_static check` | Report whether TransLink has published a new static GTFS file |
| `python -m brispulse.gtfs_static import` | Download, validate and load the static GTFS file if it changed |
| `python -m brispulse.gtfs_static import --file PATH` | Load a zip that is already on disk |
| `alembic upgrade head` | Apply database migrations |
