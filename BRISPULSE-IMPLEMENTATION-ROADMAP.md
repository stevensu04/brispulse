# BrisPulse — Implementation Roadmap

The single record of actual progress. The product vision lives in the [Master Plan](BRISPULSE-MASTER-PLAN.md); the technical design in the [Architecture](BRISPULSE-ARCHITECTURE.md); notable changes in the [Changelog](BRISPULSE-CHANGELOG.md). Any model or developer working on BrisPulse updates **this** file rather than keeping a separate roadmap.

**Last updated:** 2026-11-16

## Status at a glance

| Milestone | Status | Notes |
| --- | --- | --- |
| M0 Technical Discovery | **Done** (2026-11-16) | Five discovery documents and probe scripts |
| M1 Architecture Validation | **Done** (approved 2026-11-16) | [Architecture](BRISPULSE-ARCHITECTURE.md) §13 records the decisions; hosting (A5) and TransLink contact (A6) remain open |
| M2 Data Pipeline and Backend | **In progress** — M2.1 to M2.5 done on branch `m2-data-pipeline` | Only M2.6 (deployment) and the 24-hour live run remain, and both need an always-on machine: **blocked on the hosting decision (A5)** |
| M3 Mobility Monitoring Dashboard | Not started | |
| M4 Mobility Analytics | Not started | Needs collected history from M2 |
| M5 Production Readiness and Deployment | Not started | |

**What exists in code:** the backend skeleton, the static GTFS importer and the real-time collector (fetch, validation, freshness rules, fetch log), with tests. It also serves the live data through a JSON API (`/api/v1`) and records history (per-trip delay summaries, five-minute network samples with real-time coverage, alert history, daily per-route rollups). **What does not exist yet:** the web app, analytics endpoints over the stored history, and any deployment. No history has accumulated: the service has only run for short tests on a developer's machine.

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
- [ ] A5 Hosting provider and budget — **open, owner to decide** (needed before M2.6)
- [ ] A6 Contact TransLink — **open, owner action** (needed before public launch)

## M2 — Data Pipeline and Backend (in progress; detail in Architecture §14)
- [x] M2.1 Project skeleton, CI, container, migrations (2026-11-16)
- [x] M2.2 Static importer (2026-11-16). Verified against the live TransLink file: 553 routes, 13,125 stops, 173,183 trips, no rejected rows; version switch, rollback retention and failure cases covered by tests
- [x] M2.3 Collector with validation and freshness — code and tests (2026-11-16). Verified on real data: the three saved morning snapshots and a short live run
- [ ] M2.3 24-hour live run against TransLink — **not done**; needs the service left running for a day, then a review of `feed_fetch`
- [x] M2.4 Live API (2026-11-16): `status`, `overview`, `vehicles`, `routes`, `trips`, `alerts`, `meta/metrics`. Contract tests against the published schemas in four data conditions; "null, never zero" proven by tests; checked against live TransLink data
- [x] M2.5 Aggregator and history tables (2026-11-16): `trip_record`, `network_sample`, `alert_record`, `route_day_stats`; hourly rollup of closed service days and retention; real-time coverage in `/api/v1/overview`. Verified on live data, including a stop-and-restart
- [ ] M2.6 Early deployment of the collector; one-week data review; database backups with a tested restore; external uptime check with owner notification (Architecture §17, W2 and W3)

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

## M3–M5
Scope as in the Master Plan §8. Detailed steps will be added here when M2 is under way.

## Open owner actions
- **A5 — Choose hosting and a monthly budget.** Needed before M2.6. Requirements: an always-on container that does not sleep when idle, about 512 MB RAM, PostgreSQL with at least 1 GB. Current prices were not verified.
- **A6 — Email `translink.opendata@tmr.qld.gov.au`** to supply contact details and confirm attribution wording. Required by the open-data terms before public launch.
- Revisit the metric thresholds after the first week of collected data (A3).
- **Rate limiting** (Architecture W10): not built into the application. Responses are served from memory in milliseconds and carry cache headers; a per-IP limit belongs at the host's proxy, so it is decided together with hosting (A5).
- Update the portfolio page, which still describes the earlier event-day concept.
