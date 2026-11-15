# BrisPulse — Changelog

Notable project changes, newest first. Planning and research entries are included until application code exists.

## 2026-11-16

### M1 — Architecture proposed (Fable 5.2)
- Added `BRISPULSE-ARCHITECTURE.md` (status: proposed, awaiting owner approval).
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
