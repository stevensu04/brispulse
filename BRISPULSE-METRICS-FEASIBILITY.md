# BrisPulse — Metrics Feasibility (M0)

**Phase:** M0 — Technical Discovery
**Author:** Sonnet 5.5
**Date:** 2026-11-16
**Basis:** the live observations in [`BRISPULSE-DATA-SOURCE-RESEARCH.md`](BRISPULSE-DATA-SOURCE-RESEARCH.md) (one weekday-morning snapshot, 2026-11-16 08:41 AEST). Numbers here are illustrations of feasibility, not benchmarks.

Legend: **[V]** verified in the snapshot · **[A]** assumption or proposal for Fable to validate.
Verdicts: **Feasible** (data is available and the definition is sound) · **Feasible with caveats** · **Needs history** (requires BrisPulse to collect data over time) · **Not feasible from this data**.

Thresholds and definitions below are **proposals**. Decisions belong to M1.

---

## 1. Summary

| # | Metric (Master Plan §5.1) | Verdict | Data needed | Main caveat |
| --- | --- | --- | --- | --- |
| M1 | Active vehicle count | **Feasible with caveats** | VehiclePositions | Needs a staleness threshold; stale records exist (max 9,157 s) |
| M2 | Active service alerts | **Feasible with caveats** | Alerts | Must evaluate `active_period`; naive count is ~47 % too high |
| M3 | Route-level delay distribution | **Feasible with caveats** | TripUpdates + static GTFS | Predicted not actual; no trip-level delay field; future trips and outliers |
| M4 | Reported delay summaries (median, max, count delayed) | **Feasible with caveats** | as M3 | Same; median alone hides tails |
| M5 | Service reliability / on-time performance | **Not feasible as "on-time performance" from a snapshot; a labelled predicted-punctuality proxy is feasible; true OTP needs history** | TripUpdates + schedule (+ history of VP `STOPPED_AT` for actuals) | Master Plan §5.1 forbids calling a snapshot "definitive" |
| M6 | Service disruption statistics | **Feasible with caveats** | Alerts (+ history) | Alert feed is mostly planned works |
| M7 | Historical trends | **Needs history** | Own collected aggregates | Nothing historical exists upstream |
| M8 | Real-time coverage (proposed, supports §3.1C) | **Feasible** | VP + TU + static | Proposal, not in the Master Plan list |
| — | Crowding / spatial pressure (original concept) | **Not feasible** | — | No occupancy or crowd fields; other sources unverified |
| — | Road congestion | **Not feasible and prohibited** (§4.5) | — | — |
| — | Cancellation counts | **Not feasible yet** | — | 0 `CANCELED` observed; semantics unknown |

## 2. Metric details

Each metric uses the documentation template from Master Plan §5.2.

### M1 — Active vehicle count
- **Definition (proposed):** number of `VehiclePosition` entities for which `header.timestamp − vehicle.timestamp ≤ T`, with valid latitude/longitude and a `trip_id` that exists in the current static GTFS. Report by mode and by route.
- **Source:** VehiclePositions, `routes.txt`.
- **Update frequency:** feed refreshes every 10–20 s **[V]**.
- **Threshold T:** [V] share of records older than 60 s = 4.3 %, 120 s = 3.7 %, 300 s = 2.7 %, 600 s = 1.9 %, 1,800 s = 0.9 %. The distribution has a long tail rather than a clear gap, so T is a judgement. **[A]** 120 s or 300 s are plausible starting values; M1 should choose one and publish it. The metric should always show the threshold and the count of excluded stale vehicles.
- **Coverage limit:** counts vehicles that *report*. 91.5 % of scheduled in-progress trips had a vehicle record in the snapshot **[V]**, so it is a lower bound on what is running, never "all vehicles".
- **Never:** show 0 when the feed is unavailable; show "unavailable".
- **Snapshot value for reference:** 1,615 entities in the feed, of which 70 were older than 60 s, leaving 1,545 within 60 s **[V]** (simple subtraction of the counts in the data research).

### M2 — Active service alerts
- **Definition (proposed):** alerts with at least one `active_period` containing "now" (a missing `start` means from the beginning, a missing `end` means open-ended). Report by `cause`, `effect`, and affected route/stop count.
- **Source:** Alerts.
- **Frequency:** 10–20 s **[V]** (observed 20 s gaps).
- **Caveats:** 45 of 66 alerts were active by period; counting all entities would give 66. Alerts reference only routes and stops, so "trips affected" cannot be derived. English text only.
- **Also:** many alerts have several future windows (e.g. recurring night works); "active now" and "scheduled soon" should be distinguished in the UI.

### M3 — Route-level delay distribution
- **Definition (proposed):** for each route, the distribution of **predicted delay at the next upcoming stop** of each *in-progress, real-time-matched* trip, in seconds. Bucket into early (< −60 s), on time (−60…+300 s), late (> +300 s), severe (> +600 s); bucket edges are proposals.
- **Source:** TripUpdates (`stop_time_update.arrival/departure.delay`), joined to `trips.txt` for the route and to `calendar*` plus `stop_times` to test "in progress".
- **Verified supporting facts:** every arrival/departure event carries `delay` **[V]**; delays reconcile with the static schedule (99.8 % exact) **[V]**; there is **no trip-level delay** **[V]**, so a representative delay per trip must be chosen and documented (next stop is the most natural; maximum over remaining stops is an alternative).
- **Caveats:**
  - **These are predictions, not observed arrivals.**
  - **Future trips are present** (1,349 TU trips not in their scheduled window vs 1,243 in progress). **[A]** They probably carry placeholder delays and must be excluded or the distribution skews to zero. Needs a test in M2.
  - **Outliers:** −6,588 s … +4,883 s **[V]**. Policy for capping, flagging or excluding must be explicit.
  - Small routes have few trips; show counts and suppress or caveat very small samples.
- **Illustrative snapshot only** (next-stop delay, all trips matched to a route, **including** future trips so likely biased toward 0): median 0 s for all modes; p90 — bus 392 s, rail 318 s, tram 116 s, ferry 6 s; maxima — bus 4,845 s, rail 988 s, tram 168 s, ferry 332 s **[V]**. These numbers should **not** be published; they exist to show that distributions are skewed and heavy-tailed.

### M4 — Reported delay summaries
- **Definition (proposed):** per route and network-wide: number of trips counted, number with predicted delay > 300 s, median, p90, maximum.
- **Source / caveats:** as M3. Report **p90 as well as median** — in the snapshot the median was 0 while p90 was several minutes **[V]**. Use the wording "reported (predicted) delay", per Master Plan §3.1B.
- **Not computed:** averages (meaningless with ±hour outliers).

### M5 — Service reliability
- **What a single snapshot supports:** a **predicted-punctuality proxy**: the share of in-progress trips whose predicted next-stop delay is within the on-time band. It must carry a label such as "predicted, snapshot" and must not be called on-time performance (§5.1).
- **What true OTP needs:** observed arrival times at timing points compared with the schedule. The feeds do not contain actual arrivals. They can be approximated by recording, over time, the moment a vehicle's `current_status = STOPPED_AT` at a `stop_id` (`STOPPED_AT` was set on 548 of 1,615 vehicles in the snapshot **[V]**). That is **[A]** an approximation limited by the 10–20 s refresh, by stale records and by buses that never report `STOPPED_AT` at a given stop. It needs history and validation, and probably a sample of stops.
- **External check [A]:** TransLink publishes official on-time-running statistics on its PT Performance Dashboard (referenced in the dataset notes). Accessibility of that data was not checked; if usable it would help validate any proxy. BrisPulse should not present its proxy as equivalent to official figures.
- **Verdict:** proxy now (clearly labelled); proper OTP is an M4 stretch dependent on history.

### M6 — Service disruption statistics
- **Definition (proposed):** counts of active alerts by effect and cause, number of routes and stops affected, and (with history) alert frequency per day.
- **Caveat [V]:** at the snapshot 52 of 66 alerts were construction or maintenance, 30 were "stop moved", and only 2 had effect "significant delays". Disruption statistics will mostly describe **planned works** unless planned and unplanned are separated (cause and effect together are a reasonable first split, **[A]** to be validated against more days).

### M7 — Historical mobility trends
- **Nothing historical is provided upstream [V]** (feeds are full-dataset snapshots; static data is replaced).
- **Raw retention is impractical [A arithmetic]:** TripUpdates is about 2.2 MB uncompressed (575 KB gzipped) per fetch; at one fetch per minute that is ≈ 3.2 GB/day uncompressed (≈ 0.8 GB/day gzipped); at the 10 s feed rate it is six times that. Vehicle Positions adds ≈ 0.36 GB/day at one fetch per minute.
- **Recommendation to validate in M1:** store **aggregates** computed at ingest (per route per interval: counts, delay percentiles, alert counts) plus a small set of raw samples for debugging, rather than raw feeds.
- **Minimum credible history:** the Master Plan says trends are shown "when sufficient data has been collected". **[A]** Even a few days of aggregates cannot show weekday/weekend patterns; the UI must say how many days of data a chart is based on and show an empty state before that.
- **Verdict:** the collector must start running early in M2 so history accumulates while the dashboard is built.

### M8 — Real-time coverage (proposed)
- **Definition:** among scheduled trips in progress now (static GTFS + calendars), the share with a TripUpdate and the share with a VehiclePosition, by mode.
- **Why:** it directly operationalises "do not claim full network coverage" (§4.5) and gives users a visible measure of how complete live data is. **[V]** Snapshot: 92.8 % TU, 91.5 % VP (buses 92.2 % / 90.8 %, rail 100 %, tram 100 %, ferry 94.7 %).
- **Caveat:** computing "in progress" needs `stop_times.txt` (≈4.7 M rows); compute once per service day per trip (first and last time) and cache.
- **Status:** a proposal outside the Master Plan's list; include only if the owner approves.

## 3. Metrics that cannot be built from this data

| Idea | Why not |
| --- | --- |
| Crowding or "spatial pressure" at stations | No `occupancy_status` or crowd field was present **[V]**. Wi-Fi and gate data are unverified. |
| Road congestion | Prohibited by §4.5; vehicle positions alone cannot show it. |
| Vehicle speed / bearing | Fields absent **[V]**. Could be derived from successive positions, but with 10–20 s refresh and stale records it would be unreliable. **[A]** Not recommended in the MVP. |
| Cancellation rate | Zero `CANCELED` trips seen; 70 `REPLACEMENT` trips unexplained **[V]**. |
| Predictions, ML forecasting, recommendations | Excluded by §3.2. |

## 4. Validation approach for Fable

1. Re-run the probe scripts over several days, including a weekend and an overnight period, and record the variability in coverage, staleness and delay distribution.
2. Test the "future trips carry zero delay" hypothesis explicitly (H4 in the data research).
3. Decide the staleness threshold (M1), the delay buckets (M3), and the outlier policy; document them in the metric definitions.
4. Write metric unit tests against saved feed fixtures: stale vehicle, missing delay, alert with multiple periods, replacement trip, trip not in static data, feed unavailable (must yield "unavailable", never zero).
5. Decide whether `STOPPED_AT` history is worth collecting for an actual-arrival proxy, and on how many stops.

## 5. Documentation requirement (Master Plan §5.2)

Every shipped metric needs a published entry with name, definition, source, calculation, update frequency, coverage and accuracy limits. This document is the starting draft for those entries; M2/M4 should produce `docs/metrics.md` in the implementation repository.
