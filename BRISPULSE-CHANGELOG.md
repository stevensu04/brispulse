# BrisPulse — Changelog

Notable project changes, newest first. Planning and research entries are included until application code exists.

## 2026-11-16

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
