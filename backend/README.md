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

**Run exactly one process.** Live state is held in memory, so do not start uvicorn with
several workers, and avoid `--reload` while collecting (each reload starts over).

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
