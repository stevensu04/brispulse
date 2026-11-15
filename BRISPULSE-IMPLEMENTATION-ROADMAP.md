# BrisPulse — Implementation Roadmap

The single record of actual progress. The product vision lives in the [Master Plan](BRISPULSE-MASTER-PLAN.md); the technical design in the [Architecture](BRISPULSE-ARCHITECTURE.md); notable changes in the [Changelog](BRISPULSE-CHANGELOG.md). Any model or developer working on BrisPulse updates **this** file rather than keeping a separate roadmap.

**Last updated:** 2026-11-16

## Status at a glance

| Milestone | Status | Notes |
| --- | --- | --- |
| M0 Technical Discovery | **Done** (2026-11-16) | Five discovery documents and probe scripts |
| M1 Architecture Validation | **Proposed — awaiting owner approval** | [Architecture](BRISPULSE-ARCHITECTURE.md) §13 lists the decisions |
| M2 Data Pipeline and Backend | Not started | Blocked on M1 approval and a hosting decision |
| M3 Mobility Monitoring Dashboard | Not started | |
| M4 Mobility Analytics | Not started | Needs collected history from M2 |
| M5 Production Readiness and Deployment | Not started | |

**There is no application code yet.** Everything in this repository is planning, research and analysis scripts.

## M0 — Technical Discovery (done)
- [x] Audit of the existing implementation: none exists; BrisPulse was a concept
- [x] TransLink data sources verified live (static GTFS and three GTFS-Realtime feeds)
- [x] Metric feasibility assessed
- [x] MVP requirements proposed
- [x] Handoff written

## M1 — Architecture Validation (awaiting approval)
- [x] M0 findings re-checked on a second live snapshot; corrections recorded (Architecture §2)
- [x] Open hypotheses tested: future-trip delay bias, replacement trips, TLS failure, static processing cost
- [x] Process model, stack, storage, data model, API contract, freshness and failure rules defined
- [x] Metric definitions revised
- [ ] **Owner approval of decisions A1–A7**
- [ ] Hosting provider and budget chosen (A5)

## M2 — Data Pipeline and Backend (planned; detail in Architecture §14)
- [ ] M2.1 Project skeleton, CI, container, migrations
- [ ] M2.2 Static importer
- [ ] M2.3 Collector with validation and freshness (24-hour live run)
- [ ] M2.4 Live API
- [ ] M2.5 Aggregator and history tables
- [ ] M2.6 Early deployment of the collector; one-week data review

## M3–M5
Scope as in the Master Plan §8. Detailed steps will be added here when M2 is under way.

## Open owner actions
- Approve or amend Architecture §13 (A1–A7).
- Choose hosting and a monthly budget.
- Email `translink.opendata@tmr.qld.gov.au` about contact details and attribution wording before public launch.
- Update the portfolio page, which still describes the earlier event-day concept.
