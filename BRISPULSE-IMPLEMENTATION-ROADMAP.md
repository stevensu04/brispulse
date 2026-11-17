# BrisPulse — Implementation Roadmap

The single record of actual progress. The product vision lives in the [Master Plan](BRISPULSE-MASTER-PLAN.md); the technical design in the [Architecture](BRISPULSE-ARCHITECTURE.md); notable changes in the [Changelog](BRISPULSE-CHANGELOG.md). Any model or developer working on BrisPulse updates **this** file rather than keeping a separate roadmap.

**Last updated:** 2026-11-17

## Status at a glance

| Milestone | Status | Notes |
| --- | --- | --- |
| M0 Technical Discovery | **Done** (2026-11-16) | Five discovery documents and probe scripts |
| M1 Architecture Validation | **Done** (approved 2026-11-16) | [Architecture](BRISPULSE-ARCHITECTURE.md) §13 records the decisions; hosting (A5) and TransLink contact (A6) remain open |
| M2 Data Pipeline and Backend | **Done for the first release** — M2.1 to M2.6; merged to `main` 2026-11-17 | Deployed at https://brispulse.onrender.com. Real wake-up on Render measured: 23 s to first answer, 35 s to live data |
| M3 Mobility Monitoring Dashboard | **Done and deployed** (2026-11-17) | Overview, live map, routes, trips, alerts, about. See the limits listed under M3 |
| M4 Mobility Analytics | **Done, reduced** (2026-11-17) | Live analytics endpoint and "where the delays are now" on the overview. Trends and daily route statistics stay out: they need stored history (Amendment 1) |
| M5 Production Readiness and Deployment | **Done** (2026-11-17) | Security headers, dependency audit, frontend linter, accessibility audit, daily smoke check, operations notes. Limits listed under M5 |

**What exists in code:** the backend skeleton, the static GTFS importer and the real-time collector (fetch, validation, freshness rules, fetch log), with tests. It also serves the live data through a JSON API (`/api/v1`) and records history (per-trip delay summaries, five-minute network samples with real-time coverage, alert history, daily per-route rollups). It now has a web app (overview, live map, routes, trips, alerts, about) served by the same container. **What does not exist yet:** any public deployment.

**Scope change (owner's decision, 2026-11-16):** the first release is a live-only dashboard on free hosting, with no stored history. The service runs without a database in that mode. The history code stays in the repository, tested and switched off. See Architecture §19 and Amendment 1 in the Master Plan.

## M0 — Technical Discovery (done)
- [x] Audit of the existing implementation: none exists; BrisPulse was a concept
- [x] TransLink data sources verified live (static GTFS and three GTFS-Realtime feeds)
- [x] Metric feasibility assessed
- [x] MVP requirements proposed
- [x] Handoff written

## M1 — Architecture Validation (done)
- [x] M0 findings re-checked on a second live snapshot; corrections recorded (Architecture §2)
- [x] Open hypotheses tested: future-trip delay bias, replacement trips, TLS failure, static processing cost
- [x] Process model, stack, storage, data model, API contract, freshness and failure rules defined
- [x] Metric definitions revised
- [x] Owner approval of A1–A4 and A7 (2026-11-16): FastAPI + PostgreSQL, single process, starting thresholds, candidate features, monorepo layout
- [x] A5 Hosting and budget — decided 2026-11-16: no paid hosting; live-only release on a free host
- [ ] A6 Contact TransLink — **open, owner action** (needed before public launch)

## M2 — Data Pipeline and Backend (in progress; detail in Architecture §14)
- [x] M2.1 Project skeleton, CI, container, migrations (2026-11-16)
- [x] M2.2 Static importer (2026-11-16). Verified against the live TransLink file: 553 routes, 13,125 stops, 173,183 trips, no rejected rows; version switch, rollback retention and failure cases covered by tests
- [x] M2.3 Collector with validation and freshness — code and tests (2026-11-16). Verified on real data: the three saved morning snapshots and a short live run
- [ ] M2.3 24-hour live run against TransLink — **not done**; needs the service left running for a day, then a review of `feed_fetch`
- [x] M2.4 Live API (2026-11-16): `status`, `overview`, `vehicles`, `routes`, `trips`, `alerts`, `meta/metrics`. Contract tests against the published schemas in four data conditions; "null, never zero" proven by tests; checked against live TransLink data
- [x] M2.5 Aggregator and history tables (2026-11-16): `trip_record`, `network_sample`, `alert_record`, `route_day_stats`; hourly rollup of closed service days and retention; real-time coverage in `/api/v1/overview`. Verified on live data, including a stop-and-restart
- [x] Live-only mode (2026-11-16): the service runs with no database, reading the schedule straight from TransLink. Verified live: HTTP in 1.6 s, schedule in 10.9 s, all feeds live 12.4 s after start; about 150 MB of memory. The Docker image also ran within a 256 MB memory limit (106 MiB used)
- [x] M2.6 Deployed live-only on Render's free web service (2026-11-17): https://brispulse.onrender.com, from `main` commit `bcd9943`. Health check, status and map checked on the live site
- [x] Measured the real wake-up time on Render (2026-11-17 22:22, after an idle spell): first answer after 23 s, all feeds live 35 s after the first request
- [ ] ~~24-hour live run, one-week data review, database backups~~ — not applicable to a live-only release (Architecture §19.5)

### Measurements from M2.2 (one run, local machine)
- Full import of the live file, including the 43 MB download: 32 s, about 240 MB peak memory.
- One imported version occupies about 50 MB in PostgreSQL (the `trip` table is 41 MB). Keeping three versions is about 150 MB; revisit the "keep 3" rule if the hosted database is small.

### Measurements from M2.3 (one live run, local laptop, Monday 2026-11-16, 12:54-17:14 AEST)
- 567 fetches, none failed, no record rejected, no anomaly flagged. One conditional request was answered `304 Not Modified`.
- **The laptop slept from 14:07 to 15:43** (confirmed in the system power log), so collection has gaps of up to 69 minutes there. The collector resumed by itself on wake. While the machine was awake (about 2 h 40 min in total) every poll ran on schedule: 30 s, 60 s and 120 s exactly.
- Data was 6-36 s old when fetched (average 10-15 s), inside the 90 s "live" limit.
- A fetch plus validation took 0.5-0.8 s on average; the slowest was 5.4 s.
- Feed sizes moved with the time of day: 989-1,694 vehicles, 1,611-2,842 trip updates, 57-88 alerts (largest in the 16:00-17:00 peak).
- The service used 92-100 MB of memory, with no growth over 4 h 20 min.
- The fetch log took about 0.44 kB per row: roughly 2 MB a day, or 65 MB for the planned 30 days.
- **This is not the 24-hour run.** It covers a weekday afternoon only, and a laptop that sleeps cannot do the 24-hour run; that needs an always-on machine (hosting decision A5) or a computer kept awake.

### Measurements from M2.4 (live, local machine, Monday 2026-11-16 about 17:30 AEST, evening peak)
- 1,584 fresh vehicles, 1,252 running trips; predicted delay median 99 s, 90th percentile 609 s.
- Largest response: the full vehicle list, 695 kB of JSON (98 kB compressed), built in about 20 ms. Other endpoints answered in 1-7 ms.
- Service memory rose to about 140 MB (from about 95 MB in M2.3) now that route, stop and trip names are held in memory.
- **Finding:** in the evening 34 of 61 active alerts were not construction or maintenance, and several of those were planned timetable changes filed under "other cause". The morning observation that alerts are mostly planned works does not hold all day, and the cause field cannot separate incidents from planned changes. The API therefore labels only "planned works" and makes no claim about the rest.

### Measurements from M2.5 (live, local machine, Monday 2026-11-16, 19:16-19:33 AEST, evening off-peak)
The five-minute tick was shortened to one minute for this test, to see several cycles quickly.
- 14 network samples over 14 minutes, every feed live throughout. About 670-715 fresh vehicles and 530-580 running trips.
- **Real-time coverage:** of 554-632 scheduled trips in progress, 91-92 % had a trip update and 88-91 % a fresh vehicle. This matches the 92-93 % and 91-92 % measured by hand in the morning.
- 746 trips recorded in 13 minutes; 48 had finished. The stored rows obeyed the design: a finished trip never keeps its raw observations, a running one always does.
- **Restart:** the service was stopped and started again. 673 in-flight trips were resumed; 493 of them went on to gain observations, each with its earlier observations intact; none lost any.
- **Rollup:** a trial run over the day's records (not saved, because the service day was not over) reduced 691 eligible trips to 247 routes in 58 ms; 42 routes had enough trips for percentiles.
- Storage after 13 minutes: `trip_record` 496 kB for 746 rows (about 0.66 kB per row while raw observations are attached). At roughly 20,000 trips a day that is on the order of 10 MB a day, and about 350 MB for 35 days. **This is an extrapolation from 13 minutes and needs a real day to confirm**; if it holds, shorten the 35-day retention on a small database.
- Service memory: about 100 MB.

## M3 — Mobility Monitoring Dashboard (done and deployed, 2026-11-17)
- [x] React + TypeScript web app in `frontend/`, served by the backend container
- [x] Overview: vehicles reporting, running trips, median predicted delay, active alerts, delay bands, by-mode table
- [x] Live map of vehicle positions, coloured by delay band, with mode filter and a detail panel showing the trip's next stops
- [x] Routes list (search, mode filter) and route detail (running trips, alerts); trip detail
- [x] Alerts list
- [x] About page: metric definitions and attribution, read from the API
- [x] Loading, waking-up, unavailable, error and empty states; freshness shown on every data view
- [x] Light and dark themes; phone (375 px) and desktop (1280 px) layouts checked in a browser
- [x] API types generated from the backend's OpenAPI document; CI fails if they drift

**Acceptance (Master Plan §8, M3):** the app uses only the real API; nothing is mocked or fabricated; loading, empty and error states exist; responsive behaviour and freshness display were checked against live TransLink data.

**Measured (local, live data, 2026-11-17):** the full container was live 5.6 s after start and used 114 MiB with a 256 MB limit. JavaScript: 91 kB compressed for the app, plus 292 kB for the map, loaded only when the map is opened. 29 frontend tests, 385 backend tests.

**Known limits:**
- The map itself has no automated test (it needs WebGL); it was checked by hand. The other views have component tests.
- Vehicles on the map cannot be selected by keyboard. The same information is reachable as text under Routes.
- No end-to-end browser test in CI (the frontend linter and automated accessibility checks were added in M5).
- The basemap comes from OpenFreeMap, a free third-party service with no guarantee.
- The "waking up" screen is covered by a test; on the live site the wait it covers was measured at about half a minute.

## M4 — Mobility Analytics (done, reduced, 2026-11-17)
Reduced by Amendment 1: only figures that need no stored history.
- [x] Active vehicle and alert statistics (already in `/api/v1/overview` since M2.4)
- [x] Reported delay summaries: median, 90th percentile, early / within band / late (since M2.4)
- [x] New `/api/v1/analytics/now`: routes with the most late running trips (counts, worst delay) and active alerts by effect, by cause and by most-named route
- [x] Shown on the overview as "Where the delays are now" and "Active alerts by effect", each linking to the route
- [x] Metric definition "Late trips by route" published under `/api/v1/meta/metrics` and on the About page
- [ ] ~~Historical trends, daily route statistics~~ — out of the first release: they need stored history

**Acceptance (Master Plan §8, M4):** each metric has a documented definition; all are computed from live TransLink data; nothing historical is shown, so nothing incomplete is presented as a trend. Tests: 7 backend tests for the endpoint, 4 frontend tests for the view.

## M5 — Production Readiness (done, 2026-11-17)
- [x] Security headers on every response: content security policy (this site plus the map tiles only), no-sniff, referrer policy, HSTS, permissions policy; tested
- [x] Caching: hashed web-app files cached for a year, the page itself revalidated; tested
- [x] Dependency audit: `npm audit` and `pip-audit` found no known vulnerabilities (2026-11-17); repeated weekly by the `Dependency audit` workflow
- [x] Frontend linter (ESLint with TypeScript, React hooks and strict accessibility rules) in CI; it found one real bug (a ref written during render in the map), fixed
- [x] Accessibility audit with axe-core in a real browser, every screen, light and dark themes, desktop and phone width. Found and fixed: delay text below 4.5:1 contrast in the light theme, a skipped heading level on the alerts page, a scrollable table unreachable by keyboard at phone width, and a flash of the wrong theme on reload. After the fixes: no violations. Structural axe checks now run in CI on every screen
- [x] Smoke check `python -m brispulse.smoke URL`, run daily against the live site by the `Smoke check (live site)` workflow
- [x] Operations notes in `DEPLOY.md`

**Acceptance (Master Plan §8, M5):** production build succeeds; critical tests pass (backend 407, frontend 38); deployment verified; environment variables documented (none required); external data failures handled; known limitations documented.

**Known limits:**
- No end-to-end browser test in CI. The map is checked by hand and by the smoke check's data checks, not by an automated browser.
- No rate limiting (Architecture W10).
- The daily smoke check means an outage can go unnoticed for up to a day.
- Colour contrast is checked in a real browser, not in CI (jsdom has no layout).

## Open owner actions
- **TransLink's reply** to the approval request sent on 2026-11-17. If they ask for different attribution wording or conditions, the text is in `backend/brispulse/api/views.py` and on the About page.
- **Merge `m4-m5-finish` into `main`** to deploy M4 and M5: Render redeploys every commit to `main`.
- **iCloud copies**: files such as `frontend/src/App 2.tsx` and `backend/uv 2.lock` are duplicates created by iCloud Drive. They are now ignored by git and can be deleted.
- **GitHub commit email**: the merge commit `9925d34` (UQ address) is still reachable by its hash; left as is by the owner's decision of 2026-11-17.
