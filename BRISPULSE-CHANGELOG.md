# BrisPulse — Changelog

Notable project changes, newest first. Planning and research entries are included until application code exists.

## 2026-11-17

### Host chosen: Render free web service (deployment config added)
- Chosen because it is the only option read on 2026-11-16 that is free without a trial limit, runs a Docker image, and has no database requirement for the live-only release. Per Render's docs (blueprint spec, free page): 0.1 CPU and 512 MB, 750 free instance hours a month, spins down after 15 minutes without inbound traffic, Singapore region available.
- Added `render.yaml` (a Blueprint: Docker web service, free plan, Singapore, health check on `/healthz`, redeploy on every commit to `main`) and `DEPLOY.md`.
- Measured locally with the image limited to Render's free CPU and memory: web server up after 17 s, timetable loaded after 43 s, live data after 46 s, 110 MiB of memory. Add Render's own wake-up of about a minute: a first visit after an idle spell waits one to two minutes.
- Not done: the account and the first deploy. They need the owner's Render account, and `main` does not yet contain the web app.
- Not verified: Render's build limits for free Docker services, and whether its health check tolerates the 17 s start-up; neither is stated in the pages read.

### M3 — Web app (Fable 5.2)
- Added the dashboard in `frontend/`: overview, live map, routes and route detail, trip detail, alerts, and an about page with the metric definitions. React, TypeScript, Vite; MapLibre for the map.
- The backend now serves the built web app, so one container is the whole product. The Docker image builds both.
- Interface rules: an unknown value is shown as "Unavailable" with the API's reason, never as zero; freshness is shown on every data view as an icon and a word; delay is written in words and described as a prediction.
- A "waking up" screen for hosts that sleep, shown while requests are being retried.
- Light and dark themes; phone and desktop layouts.
- The web app's types are generated from `backend/openapi.json`; a backend test and a CI step fail if the API, that file or the types disagree.
- Decisions: basemap tiles from OpenFreeMap (free, no key, attribution shown; closes Architecture W11); TypeScript pinned to 5.9 because the API type generator needs the TypeScript 5 compiler API; a hand-written hash router instead of a routing library; plain CSS with design tokens.
- Found and fixed while checking in a browser: the map had zero height because the map library's own CSS overrode the layout; vehicle dots were too small to tap, so a tap now selects the nearest vehicle within a 44 px area; the freshness line quoted the age of the slowest feed (alerts) instead of the vehicle feed; the waking-up screen did not appear during retries.
- Tests: 29 frontend, 385 backend.

## 2026-11-16

### Scope change — live-only first release (owner's decision)
- After comparing hosting costs, the product owner decided not to pay for hosting. The first release is a live dashboard on a free host; stored history, trends, daily route statistics and real-time coverage are out of it. Recorded as Amendment 1 in the Master Plan and as Architecture §19.
- Added a live-only mode: with no `DATABASE_URL` the service runs without any database. It reads the schedule straight from TransLink's zip at start-up (only the three small files it needs), keeps everything in memory and stores nothing.
- The service now starts answering at once and reports that it is loading; the collector begins polling as soon as the schedule is in memory instead of a full interval later.
- `/api/v1/status` reports `history_enabled`; coverage in the overview is `null` with a note when no history is kept.
- The container honours a `PORT` variable set by the host.
- The history code from M2.5 is unchanged, tested and off; configuring a database turns it on.
- Measured against live TransLink: all three feeds live 12.4 s after the process starts, about 150 MB of memory.
- Tests: 382 in total.
- Hosting prices read from the vendors' pages on 2026-11-16, for the record: Railway Hobby US$5/month including US$5 of usage (no Australian region); DigitalOcean 1 GB Droplet US$6/month (Sydney available); Fly.io shared-cpu-1x 512 MB US$3.69/month at its base region with a 1.269 multiplier in Sydney, managed Postgres from US$38/month, invoices under US$5 waived. Render's prices could not be read from its page.

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
