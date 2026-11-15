# BrisPulse

A Brisbane mobility intelligence platform built on TransLink's open public transport data.

> **Status: planning.** There is no application code in this repository yet. It currently holds the product plan, technical discovery, an approved architecture and the analysis scripts used to verify the data. Progress is tracked in the [Implementation Roadmap](BRISPULSE-IMPLEMENTATION-ROADMAP.md).

## What it aims to do

Show what is happening on the South East Queensland public transport network now, which routes are delayed or disrupted, and how conditions change over time — using real data, with clear indications of how fresh and how complete that data is.

## Documents

| Document | Purpose |
| --- | --- |
| [Master Plan](BRISPULSE-MASTER-PLAN.md) | Product vision, scope and milestones |
| [Implementation Roadmap](BRISPULSE-IMPLEMENTATION-ROADMAP.md) | Actual progress |
| [Architecture](BRISPULSE-ARCHITECTURE.md) | Approved technical design |
| [Changelog](BRISPULSE-CHANGELOG.md) | Notable changes |

Discovery (M0): [Repository Audit](BRISPULSE-REPOSITORY-AUDIT.md) · [Data Source Research](BRISPULSE-DATA-SOURCE-RESEARCH.md) · [Metrics Feasibility](BRISPULSE-METRICS-FEASIBILITY.md) · [MVP Requirements](BRISPULSE-MVP-REQUIREMENTS.md) · [Technical Handoff](BRISPULSE-TECHNICAL-HANDOFF.md)

Scripts used to verify the live feeds are in [`discovery/probes/`](discovery/probes/).

## Data and attribution

BrisPulse uses Translink GTFS and GTFS-Realtime data published by the State of Queensland (Department of Transport and Main Roads) under a [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/) licence. See [Translink open data](https://translink.com.au/about-translink/open-data).

BrisPulse is an independent project. It is not affiliated with or endorsed by Translink or the State of Queensland, which give no warranty about the accuracy, completeness or currency of the data.
