# BrisPulse — MVP Requirements (M0 proposal)

**Phase:** M0 — Technical Discovery
**Author:** Sonnet 5.5
**Date:** 2026-11-16
**Status:** **Proposal.** Requirements below refine Master Plan §3 and §9 using verified findings. Anything that changes product direction or MVP scope needs product-owner approval (Master Plan §15); such items are marked **[Decision]**.

Evidence references: [Audit](BRISPULSE-REPOSITORY-AUDIT.md) · [Data research](BRISPULSE-DATA-SOURCE-RESEARCH.md) · [Metrics](BRISPULSE-METRICS-FEASIBILITY.md).

---

## 1. Feasibility verdict

**The MVP in the Master Plan is realistic on data grounds, and not constrained by access:**
- The three feeds and the static schedule are free, unauthenticated, joinable (100 % ID match in the snapshot) and refresh every 10–20 s.
- Every MVP feature in §3.1 has a data source, with caveats listed in the metrics document.

**It is less certain on engineering grounds, for three reasons:**
1. **Greenfield.** There is no code to build on (audit §1). Nothing in the schedule should assume reuse.
2. **Operational shape.** Ingesting every 10–60 s and accumulating history needs a scheduled or always-on process, plus storage for aggregates. This does not fit a purely static or serverless-only deployment (Master Plan §12 already flags this). The decision is M1's.
3. **History starts at zero.** Trend features cannot be demonstrated until the collector has run for a meaningful time (metrics M7).

No time estimates are given here: none can be justified from the evidence gathered.

## 2. Scope

### 2.1 In scope (MVP)

| ID | Capability | Master Plan ref | Verified data basis |
| --- | --- | --- | --- |
| F1 | Network overview: counts of fresh active vehicles by mode, active alerts, last-updated time | §3.1A | VP, Alerts |
| F2 | Interactive map of fresh vehicle positions, filterable by mode and route | §3.1A | VP lat/lon, `routes.txt` |
| F3 | Route list and route detail (name, mode, vehicles currently reporting, active alerts, reported delay summary) | §3.1A | `routes.txt`, VP, TU, Alerts |
| F4 | Service alerts list with cause, effect, affected routes/stops, active periods, link to source URL | §3.1A | Alerts |
| F5 | Reported (predicted) delay information per route/trip, labelled as predicted | §3.1A/B | TU + static |
| F6 | Data freshness indicators on every view (feed timestamp, age, state: live / delayed / stale / unavailable) | §3.1A/C | feed headers |
| F7 | Descriptive analytics: active vehicles, active alerts, route-level delay distribution, delay summaries, disruption statistics | §3.1B | M1–M4, M6 |
| F8 | History collection from day one of M2; trend views only when enough data exists, with an honest empty state | §3.1B, §5.1 | own aggregates |
| F9 | Data-reliability behaviour: distinguish live vs scheduled, stale/missing handling, upstream-failure handling, no zeros for unavailable data, timestamps recorded | §3.1C | §5 of data research |
| F10 | Metric definitions page and an "About this data" page with attribution, limitations and disclaimer | §5.2, §4.5 | T&C |

### 2.2 Candidate additions needing a decision

| ID | Item | Why it is raised | Recommendation |
| --- | --- | --- | --- |
| **[Decision] C1** | Real-time coverage indicator (metrics M8) | Operationalises "no full-coverage claims" | Include in F6/F9; low cost, high honesty value |
| **[Decision] C2** | Predicted-punctuality proxy (metrics M5) | Gives a reliability view without claiming OTP | Include **only** if clearly labelled; otherwise defer |
| **[Decision] C3** | Actual-arrival proxy from `STOPPED_AT` history | Needed for true OTP | **Defer** past MVP |
| **[Decision] C4** | Rail/ferry/tram detail pages | Small fleets; rail 88 vehicles, ferry 25, tram 16 in snapshot | Treat as filters on F2/F3, not separate features |

### 2.3 Out of scope (unchanged from Master Plan §3.2)
AI/ML prediction, automated or personalised recommendations, congestion analysis, multi-modal journey planning, smart-city decision support, user accounts. Also out: **crowd or spatial-pressure scoring and spatial-equity routing** (original concept) — no supporting data, and routing is excluded.

## 3. Functional requirements

Priority: **M** must · **S** should · **C** could.

### 3.1 Ingestion and data layer
| ID | Requirement | Pri |
| --- | --- | --- |
| R1 | Fetch VP, TU and Alerts for SEQ without credentials, no more often than the feed refreshes (≥ 10 s) | M |
| R2 | Decode GTFS-RT v2.0 Protobuf; reject or flag undecodable responses | M |
| R3 | Load and refresh GTFS static; detect version change by `Last-Modified`/`ETag`/`feed_info.txt` and pair real-time data with the correct schedule | M |
| R4 | Validate every record (IDs resolvable, coordinates inside SEQ bounds, timestamps plausible) and record rejects with reasons | M |
| R5 | Persist retrieval metadata per fetch: timestamp, HTTP status, header timestamp, entity counts, duration | M |
| R6 | Store aggregates and alert history for trends; raw snapshots only as a bounded sample | S |
| R7 | Tolerate upstream failure: serve last good data marked stale, never invent data | M |
| R8 | Apply `Accept-Encoding: gzip` on fetches (TU 2.2 MB → 575 KB) | S |

### 3.2 API
| ID | Requirement | Pri |
| --- | --- | --- |
| R9 | Application API returns validated, normalised JSON; contract is defined before frontend work | M |
| R10 | Every response includes `source_timestamp`, `fetched_at`, `age_seconds` and a `freshness` state | M |
| R11 | Unavailable values are `null` with an explicit reason, never `0` | M |
| R12 | Errors do not leak internals or configuration | M |

### 3.3 Frontend
| ID | Requirement | Pri |
| --- | --- | --- |
| R13 | Overview, map, route detail, alerts, analytics and "About this data" views | M |
| R14 | Loading, empty, error, stale and unavailable states for every data view | M |
| R15 | Map handles ≈1,600 markers acceptably on a phone (clustering or filtering) | M |
| R16 | Delay labelled "predicted" wherever shown; thresholds visible | M |
| R17 | Responsive layout, accessible contrast, status never conveyed by colour alone | M |
| R18 | Attribution and disclaimer visible; no Translink logo without approval | M |

### 3.4 Analytics
| ID | Requirement | Pri |
| --- | --- | --- |
| R19 | Each metric implements the definition in the metrics document or a revised version approved in M1 | M |
| R20 | Trend views show the number of days of data and refuse to draw trends below a minimum, which M1 defines | M |
| R21 | Outlier policy (e.g. delays beyond ±1 hour) is explicit and disclosed | M |

## 4. Non-functional requirements

| ID | Requirement |
| --- | --- |
| N1 | **Truthfulness:** no fabricated or mock data in any shipped feature (§4.5, §9). Test fixtures are labelled as fixtures and never reachable in production. |
| N2 | **Security:** no secrets in git; environment variables documented; validate all external data. |
| N3 | **Testing:** parsing, validation, metrics, API and critical end-to-end paths (§10). Fixtures from real saved feeds covering the hazards H1–H10 in the data research. |
| N4 | **Operations:** structured logging of fetch outcomes; health information that shows feed age and last successful ingest. |
| N5 | **Cost:** run on free or low-cost hosting for the MVP. **[A]** Not assessed; part of M1. |
| N6 | **Documentation:** architecture, data sources, API contract, metric definitions, environment config, deployment, limitations (§10). |
| N7 | **Compliance:** CC BY 4.0 attribution, no endorsement claim, third-party disclaimer, logo approval, contact-details obligation (data research §8). |

## 5. Acceptance criteria (mapped to Master Plan §9)

| Master Plan §9 | Concrete, testable criterion |
| --- | --- |
| Real transport data integrated | A deployed instance shows vehicles whose IDs resolve to the current TransLink schedule and whose feed timestamp is within one polling window |
| Traceable source and timestamps | Each API response and UI view exposes source timestamp and fetch time |
| Validation | Unit tests prove stale, malformed and unmatched records are rejected or flagged, per R4 |
| Missing and stale handled | Disabling the upstream (simulated) shows stale then unavailable states, and no zeros |
| Application APIs and tests | Contract tests pass; fixtures cover H1–H10 |
| Secrets not exposed | Repository scan shows none; no key is needed by design |
| Frontend usable on mobile and desktop | Checked at phone and desktop widths with all R14 states reachable |
| Analytics from genuine data | Each metric traceable to a documented definition; trend view hidden below the minimum data |
| Upstream failure does not crash | Chaos test: block the feed; app keeps serving last-good with a stale flag |
| Public deployment | URL reachable; production build succeeds; env vars documented; limitations listed |

## 6. Risks (MVP-level)

| ID | Risk | Likelihood / impact | Mitigation |
| --- | --- | --- | --- |
| K1 | No existing code; prior schedule assumed reuse | Certain / medium | Plan as greenfield |
| K2 | Ingestion doesn't fit serverless | Likely / high | M1 chooses hosting and process model first |
| K3 | History too short at launch for trends | Likely / medium | Start the collector early; show honest empty states |
| K4 | Delay metrics distorted by future trips and outliers | Likely / high | Test hypothesis H4; explicit exclusion rules; disclose |
| K5 | Upstream can change or remove data without notice | Possible / high | Schema validation, alerts on feed anomalies, documented disclaimer |
| K6 | Storage growth if raw feeds are kept | Likely / medium | Aggregate at ingest; bounded raw samples |
| K7 | Portfolio copy contradicts new direction | Certain / medium | Update after repo is public |
| K8 | T&C obligations (contact details, attribution wording) unfulfilled | Possible / medium | Clarify with TransLink before launch |
| K9 | Map performance with ≈1,600 vehicles | Possible / low | Clustering, viewport filtering |

## 7. Decisions needed from the product owner

| ID | Decision | Needed by |
| --- | --- | --- |
| P1 | Confirm the pivot from the event-day pressure concept to the Mobility Intelligence direction as the public story | Before the portfolio page changes |
| P2 | Approve or reject candidates C1–C4 | M1 |
| P3 | Where the prototype source lives, if anywhere (audit Q1) | M1 |
| P4 | Hosting budget and preference (the owner's earlier plan named Railway/Fly.io; EventNow runs Django + HTMX on Vercel) | M1 |
| P5 | Whether to register contact details and agree attribution wording with TransLink (`translink.opendata@tmr.qld.gov.au`) | Before public launch |
| P6 | Whether to audit the DECO7380 reports for citeable user research | Optional |

## 8. Traceability to Master Plan milestones

| Milestone | Delivers requirements |
| --- | --- |
| M1 Architecture | decisions on R3, R6, N5; API contract for R9–R12; metric thresholds for R19–R21 |
| M2 Pipeline and backend | R1–R12, N2–N4 |
| M3 Dashboard | R13–R18, F1–F6 |
| M4 Analytics | R19–R21, F7–F8 |
| M5 Production | N3–N7, deployment criteria |
