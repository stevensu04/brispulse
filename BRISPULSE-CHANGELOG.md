# BrisPulse — Changelog

Notable project changes, newest first. Planning and research entries are included until application code exists.

## 2026-11-16

### M2.5 — History (Fable 5.2)
- Four new tables: `trip_record` (one row per trip per service day, summarising its delay observations), `network_sample` (network state every five minutes, per mode), `alert_record` (each alert's content and when it was seen; reworded alerts get a new row) and `route_day_stats` (per-route daily rollup).
- The unit for route statistics is the trip: each trip contributes its own median delay, and only if it was observed at least three times. Percentiles need at least five trips.
- Real-time coverage (scheduled trips in progress that have live data) is computed with each network sample and shown in `/api/v1/overview`. The schedule lookup handles service days that run past midnight and calendar exceptions.
- Data too old to trust is not written as history: a stale feed leaves its figures empty for that sample. History has gaps where collection had gaps.
- A trip counts as finished once ten minutes of newer data have been seen without it, judged against the data's own timestamps rather than the clock, so an interruption in collection (such as the laptop sleeping in the M2.3 run) does not close trips that are still running.
- On shutdown, in-flight trips are written with their observations; on start-up they are resumed. If the database is unreachable, trip summaries are held and retried.
- Hourly maintenance rolls up closed service days and applies retention (30 days for the fetch log; 35 days for trip records, deleted only once their day has been rolled up).
- Tests: 365 in total. Verified against live data, including a stop-and-restart and a trial rollup; details in the roadmap.
- Not done: analytics endpoints over the stored history (planned for M4), and any accumulated history, which needs the service to stay running.

### M2.4 — Live API (Fable 5.2)
- Added the read-only JSON API under `/api/v1`: `status`, `overview`, `vehicles`, `routes`, `routes/{id}`, `trips/{id}`, `alerts`, `meta/metrics`, with generated OpenAPI documentation at `/docs`.
- One envelope for every response (`data` and `meta`), one shape for every error. `meta` states how fresh each underlying feed is. Unavailable values are `null` with a note, never `0` or an empty list; a real zero is only reported when live data supports it.
- Delay summaries use the running-trip population, nearest-rank median and 90th percentile, and counts early, within band and late. Implausible delays are excluded and counted. Fewer than five trips gives counts but no percentiles.
- Live endpoints read only from memory, so they keep working if the database is down. Responses carry `Cache-Control` and a weak `ETag`; large responses are gzip-compressed.
- Tests: 306 in total. Every endpoint is validated strictly against its schema in four conditions (live, nothing fetched, everything too old, vehicles only).
- Found by running against live data and fixed: a running trip could show no vehicle ID when its trip update named none; and the alert label "planned" was renamed "planned works" because other alerts are not necessarily incidents (see the roadmap).
- Rate limiting is deferred to the hosting decision. Analytics endpoints and real-time coverage wait for M2.5, which stores history.

### M2.3 — Real-time collector (Fable 5.2)
- The running service now polls TransLink's three GTFS-Realtime feeds, validates every record against the static schedule, keeps the current picture in memory and writes one row per fetch to a new `feed_fetch` table.
- Validation rules cover each hazard found in discovery: stale and long-silent vehicles, positions outside South East Queensland, future timestamps, records that do not match the schedule, delays beyond an hour, cancelled and replacement trips, alerts with several active periods or unknown stops.
- "Running trip" is defined in one place (`realtime/populations.py`): matched to the schedule, not cancelled, scheduled start passed, and a fresh vehicle reporting. On the saved morning snapshots it gives 1,222 and 1,068 running trips, the same as the M1 probe; on the third it gives 994 against the probe's 992, because the probe mishandled two trips that had both a fresh and a stale vehicle record.
- A failed or unusable response never replaces good data; the previous snapshot stays and its freshness state degrades with age.
- The service imports the static schedule by itself at start-up and every six hours, in a subprocess.
- Tests: 204 in total, including a 176 kB sample of real TransLink data (attributed in `backend/tests/fixtures/README.md`).
- Live run: 4 h 20 min on a laptop, 567 fetches, none failed. The laptop slept for about 1 h 36 min in the middle, which shows as gaps in the log. The planned 24-hour run is still outstanding. Details in the roadmap.
- Not yet user-visible: there is still no API or web page showing this data (M2.4, M3).

### M2.1 and M2.2 — Backend skeleton and static importer (Fable 5.2)
First application code, on branch `m2-data-pipeline`.
- Backend project: FastAPI app with a liveness probe, settings, PostgreSQL models and the first Alembic migration, Docker image, local `docker-compose` database, GitHub Actions CI (lint, format, type check, tests against PostgreSQL, container build).
- Static GTFS importer (`python -m brispulse.gtfs_static`): checks TransLink for a new file, downloads it, validates every row, reduces 4.67 million stop-time rows to one span per trip, and loads the result as a new version in a single transaction. Refuses empty or sharply smaller feeds; keeps the last three versions.
- Verified against the live file: counts match M0 exactly, and an SQL query for "scheduled trips in progress" reproduces the M0 and M1 probe results (1,243 at 08:41, 1,029 at 09:17).
- Deviations from the approved architecture, both small:
  - **`httpx2` instead of `httpx`.** The installed Starlette deprecates `httpx` for its test client and names `httpx2` (same author, same API) as the replacement. Using one HTTP library throughout avoids carrying both.
  - **Flat package layout** (`backend/brispulse/`, no `src/`), because macOS ignores editable-install files in cloud-synced folders.

### M1 — Post-approval review (Fable 5.2)
- Added a third live snapshot (09:17 AEST) to the architecture's validation section; figures were consistent with the first two.
- Added a self-review of weaknesses and gaps (no database backup plan, no notification when the collector stops, unspecified rate limiting, undecided map tiles) and a list of what is preserved from the original concept.

### M1 — Architecture approved
- The product owner approved the architecture: FastAPI + PostgreSQL, a single always-on process, the starting metric thresholds, the candidate features and the monorepo layout.
- Left open: hosting and budget (A5), and contacting TransLink (A6).

### M1 — Architecture proposed (Fable 5.2)
- Added `BRISPULSE-ARCHITECTURE.md`.
- Added `BRISPULSE-IMPLEMENTATION-ROADMAP.md`, this changelog and a README.
- Added probes `m1_verify.py`, `m1_population.py`, `m1_static_cost.py`.
- Corrections to M0 findings, from a second live snapshot (09:03 AEST):
  - Delay statistics must exclude trips that have not started: those without a vehicle report zero delay about 95 % of the time, and those with a waiting vehicle report large negative values. Among running trips the median predicted next-stop delay was 118 s in both snapshots.
  - `REPLACEMENT` trips were all rail and behave like running trips.
  - One `CANCELED` trip was observed.
  - The Python TLS failure was a missing CA bundle in the local Python build, not a TransLink problem.
  - `If-Modified-Since` yields `304`; `If-None-Match` is ignored.

### M0 — Technical discovery completed (Sonnet 5.5)
- Added the five discovery documents and four probe scripts.
- Recorded that no BrisPulse code exists; the project was a concept only (confirmed by the owner).
- Repository created and published.

### Project start
- Added `BRISPULSE-MASTER-PLAN.md` (v1.0).
