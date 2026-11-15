# BrisPulse — Technical Handoff to Fable 5.2 (M0 → M1)

**From:** Sonnet 5.5 · **Date:** 2026-11-16 · **Phase completed:** M0 — Technical Discovery
**Read first:** [`BRISPULSE-MASTER-PLAN.md`](BRISPULSE-MASTER-PLAN.md). Then, in order: [Audit](BRISPULSE-REPOSITORY-AUDIT.md), [Data research](BRISPULSE-DATA-SOURCE-RESEARCH.md), [Metrics](BRISPULSE-METRICS-FEASIBILITY.md), [MVP requirements](BRISPULSE-MVP-REQUIREMENTS.md).

Master Plan §7.2 expects you to challenge these findings rather than accept them. The "verify first" list in §4 is where I would start.

---

## 1. State of the project

- **There is no BrisPulse code.** Searched: the portfolio repo, the owner's GitHub account (12 repos, none named BrisPulse), and the local machine. The only artefacts are a portfolio case-study page, a screenshot of a mock-looking mobile UI, and a *proposed* Django/GTFS-R stack. M1 is greenfield.
- **The Master Plan is a change of direction** from the original event-day crowd-pressure concept to a transport-data Mobility Intelligence platform. The crowd-pressure data (Wi-Fi probes, gate egress) was never verified and is not in the MVP.
- This repository (`brispulse/`, local folder `UQ NOTES/DECO7380/brispulse`) contains only the Master Plan, the five M0 documents and four probe scripts. **No application source code was created or modified.** The portfolio repository was not changed.

## 2. What is verified (live, 2026-11-16 08:41 AEST, one snapshot)

| Fact | Detail |
| --- | --- |
| Open access | SEQ GTFS static and GTFS-RT (VehiclePositions, TripUpdates, Alerts) return HTTP 200, **no key**, `Cache-Control: max-age=10`. GTFS-RT v2.0, Protobuf, FULL_DATASET. |
| Refresh | Header timestamps change every 10–20 s (alerts 20 s). |
| Size | VP 253 KB; **TU 2.2 MB (575 KB gzipped)**; Alerts 30 KB; static zip 43.4 MB, `stop_times.txt` 4.67 M rows. Static feed window 2026-11-14 → 2027-01-13. |
| Scale | 1,615 vehicles, 2,503 trip updates, 66 alerts. Routes: bus 476, rail 67, ferry 9, tram 1 in `routes.txt`. |
| Joins | Every VP/TU route, trip and stop ID matched the static zip. Alerts: all routes matched, 74/75 stops. |
| Delay semantics | Delay is stop-level only (no trip-level). `predicted time − delay` equals the static schedule for 99.8 % of 85,008 events. Delays are **predictions**. |
| Coverage | 92.8 % of scheduled in-progress trips had a TripUpdate; 91.5 % a VehiclePosition. |
| Missing fields | No occupancy, bearing, speed, congestion in VP; no trip-level delay in TU. |
| Licence | CC BY 4.0 + Queensland open-data T&C: attribution, no endorsement claim, logo approval, "keep contact details current", no warranty, data can change without notice. |

## 3. Hazards found (need design answers)

Stale vehicle timestamps up to 9,157 s in a fresh feed · TripUpdate entity timestamps up to 19,394 s old · delays from −6,588 s to +4,883 s · trips not yet running included in TripUpdates · 70 `REPLACEMENT` trips with unexplained meaning · alerts with several `active_period` windows (45 of 66 active; mostly planned works) · catalogue metadata (CKAN) wrong about format, size and update frequency · one alert stop ID absent from `stops.txt` · schedule rolls over on a rolling window.

## 4. Verify first (I could not, or did not)

1. **Longer observation.** Everything above is one snapshot. Re-run `discovery/probes/` over days, including weekends, overnight and a disruption. Record how coverage, staleness and delay behave.
2. **Future-trip hypothesis.** I think TripUpdates for not-yet-started trips carry placeholder (probably zero) delays and bias delay distributions. Not measured.
3. **`REPLACEMENT` semantics** and whether cancellations ever appear as `CANCELED`.
4. **Static update cadence and rollover.** Observe a replacement of `SEQ_GTFS.zip` and check whether realtime IDs break at the switch.
5. **TLS from the runtime.** Python `urllib` failed certificate verification here while `curl` succeeded (cause undiagnosed, probably environmental). Test the chosen fetcher in the real deployment runtime.
6. **Rate limits / optional API key** (`vary: X-Api-Key` header). None observed.
7. **T&C obligations:** contact-details mechanism and attribution wording. Needs the owner (contact `translink.opendata@tmr.qld.gov.au`).
8. My proposed thresholds (60/120/300 s stale; ±60/300/600 s delay buckets) are **proposals**, not evidence-backed choices.

## 5. Decisions for you (M1)

| # | Decision | Inputs |
| --- | --- | --- |
| 1 | **Process model**: always-on worker vs scheduled jobs vs serverless. Ingest cadence (10–60 s?). | TU payload size; history needs; Master Plan §12 deployment risk; owner budget (open) |
| 2 | **Storage**: what to keep (aggregates, alert history, retrieval metadata, bounded raw samples), engine, retention. | Raw TU at 1/min ≈ 3.2 GB/day uncompressed (arithmetic); `stop_times` size |
| 3 | **Static GTFS handling**: full load vs reduced subset (e.g. first/last time per trip, stops, routes, shapes on demand) | 4.67 M `stop_times` rows |
| 4 | **Stack**: Python/Django (owner's earlier proposal and existing EventNow experience) vs a JS stack vs other. There is nothing to preserve. If a Next.js frontend is chosen, its docs in `node_modules/next/dist/docs/` must be read (portfolio `AGENTS.md` warns of breaking changes). | Master Plan §6.3 criteria |
| 5 | **Metric definitions**: staleness threshold, delay buckets, outlier policy, representative per-trip delay, minimum history for trends | [Metrics](BRISPULSE-METRICS-FEASIBILITY.md) |
| 6 | **API contract** with freshness fields and `null`-never-zero semantics | [MVP requirements](BRISPULSE-MVP-REQUIREMENTS.md) R9–R12 |
| 7 | **Candidates C1–C4** and product-owner decisions P1–P6 | [MVP requirements](BRISPULSE-MVP-REQUIREMENTS.md) §2.2, §7 |

## 6. Recommended M1 sequence (suggestion, not instruction)

1. Run the longer observation (§4.1–4.4) while you read the documents.
2. Decide process model and storage (§5.1–5.3) first; everything else depends on them.
3. Fix metric definitions, then the API contract, then data models.
4. Define fixtures from real saved feeds for each hazard.
5. Write `BRISPULSE-ARCHITECTURE.md`, then ask the owner for approval before any M2 implementation (Master Plan §8 M1 acceptance).

## 7. Things to avoid (from Master Plan §4.5, confirmed relevant by the data)

- Counting every alert entity as active.
- Treating TripUpdate `delay` as an observed arrival; call it "predicted delay".
- Averaging delays across outliers; showing zero for unavailable data.
- Claiming full coverage (about 7–9 % of in-progress trips lacked real-time at the snapshot).
- Using the Translink logo or implying endorsement.
- Reusing the old crowd-pressure colours or copy for delay data without redefinition.

## 8. Repository hygiene for M1

- The Master Plan commit exists locally; the repository has **no remote yet**. The owner chose a new public GitHub repository; creating and pushing it is awaiting the owner's confirmation.
- Commits are authored only by the owner (`stevensu04`); no AI co-author trailers (owner's standing preference).
- Raw feed data was not committed. Probe scripts are in `discovery/probes/`.
- Open owner questions are consolidated in the [MVP requirements](BRISPULSE-MVP-REQUIREMENTS.md) §7 and the [Audit](BRISPULSE-REPOSITORY-AUDIT.md) §11.
