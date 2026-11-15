# BrisPulse — TransLink Data Source Research (M0)

**Phase:** M0 — Technical Discovery
**Author:** Sonnet 5.5
**Date:** 2026-11-16
**Live observations taken:** Sunday 2026-11-15 22:41–22:45 UTC (Monday 2026-11-16, 08:41–08:45 Brisbane time, AEST UTC+10 — a weekday morning peak).

Legend: **[D]** documented by an official page or metadata · **[V]** verified live in this session by calling the endpoint · **[A]** assumption / not verified.

**Important limitation:** every [V] number below comes from a **single snapshot (plus a 75-second cadence test)**. It shows what is possible and what edge cases exist. It does not describe typical behaviour across days, weekends, outages or events. Fable should re-measure over a longer window in M1/M2.

---

## 1. Summary

| Question | Answer |
| --- | --- |
| Is real Brisbane/SEQ data available? | **[V] Yes.** GTFS static zip and three GTFS-Realtime feeds returned HTTP 200 with real content. |
| Authentication? | **[D][V] None required.** TransLink's open-data page states "Authentication is not required to use the feed." Requests with no key or header succeeded. |
| Cost? | **[D]** Offered free of charge (T&C), subject to change without notice. |
| Format? | **[V]** GTFS-RT v2.0 Protobuf (`application/x-protobuf`). GTFS static is a ZIP of CSV `.txt` files. |
| Can real-time data be joined to the schedule? | **[V] Yes, 100% of IDs matched** in this snapshot (§5). |
| Is the licence compatible with a public project? | **[D]** CC BY 4.0 plus Queensland open-data T&C (§8). Attribution and a few conditions apply. |
| Is history available? | **[V] No.** Feeds are live snapshots. History exists only if BrisPulse collects it. |

## 2. Official sources

| Source | URL | Notes |
| --- | --- | --- |
| TransLink open data page | https://translink.com.au/about-translink/open-data | **[V]** Reachable. Describes schedule data, real-time data (GTFS-RT v2.0, Protobuf, "based on gtfs-realtime.proto"), CC BY 4.0, no authentication, and that real-time feeds "must be used in conjunction with GTFS schedules". |
| Terms and conditions | https://translink.com.au/about-translink/open-data/terms-and-conditions | **[V]** Read in full for this document. See §8. |
| Queensland open data: real-time | https://www.data.qld.gov.au/dataset/translink-real-time-data | **[V]** CKAN API `package_show` succeeded. Licence CC-BY-4.0. |
| Queensland open data: GTFS static | https://www.data.qld.gov.au/dataset/general-transit-feed-specification-gtfs-translink | **[V]** CKAN API succeeded. Licence CC-BY-4.0. |
| Feed host | https://gtfsrt.api.translink.com.au | **[V]** Hosts the feeds and the static zips. |

**Catalogue metadata is not reliable.** **[V]** The CKAN record lists the GTFS-RT resources as format "CSV" with size "1 bytes", and the SEQ static zip as "30 bytes" with last modified 2023-11-13, while the real files are Protobuf and a 43,401,875-byte ZIP last modified 2026-11-13. The static dataset says update frequency "annually" while the observed zip was only days old and its `feed_info.txt` window is 60 days (§4). **Do not derive size, format or freshness from the catalogue.**

## 3. Endpoints verified (SEQ)

All returned HTTP 200, no key, `Cache-Control: public, max-age=10`.

| Feed | URL | Observed size | Entities |
| --- | --- | --- | --- |
| Vehicle Positions | `https://gtfsrt.api.translink.com.au/api/realtime/SEQ/VehiclePositions` | 253,212 B | 1,615 |
| Trip Updates | `https://gtfsrt.api.translink.com.au/api/realtime/SEQ/TripUpdates` | 2,210,404 B (575,176 B with `Accept-Encoding: gzip`) | 2,503 |
| Service Alerts | `https://gtfsrt.api.translink.com.au/api/realtime/SEQ/Alerts` (lowercase `/alerts` also works) | 29,921 B | 66 |
| Static GTFS | `https://gtfsrt.api.translink.com.au/GTFS/SEQ_GTFS.zip` | 43,401,875 B | see §4 |

**Per-mode variants [V]** (documented on the open-data page, all HTTP 200): `TripUpdates/Bus` (2,043,966 B), `TripUpdates/Rail` (125,585 B), `VehiclePositions/Bus` (228,571 B), `VehiclePositions/Rail` (13,955 B), `VehiclePositions/Ferry` (4,569 B), `VehiclePositions/Tram` (2,581 B). `TripUpdates/Ferry`, `TripUpdates/Tram` and alert splits were not tested.

**Other regions [D]:** the catalogue also lists Cairns (CNS) real-time feeds and regional static feeds. Not tested; out of MVP scope (Brisbane/SEQ).

**Headers worth noting [V]:** `vary: Accept-Encoding,X-Api-Key` appears on responses. No key was required; why the header is varied on is unknown. **[A]** A key may be optional or reserved for future use; do not assume either way.

**Unexplained local TLS failure [V]:** Python's `urllib` failed with `CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain` against `gtfsrt.api.translink.com.au` in the discovery environment while `curl` succeeded. **[A]** This probably reflects the local environment's certificate store rather than TransLink; it was not diagnosed. Probe scripts therefore fetch with `curl`. A production fetcher must be tested in its real runtime.

## 4. GTFS static

**[V] Archive contents** (`SEQ_GTFS.zip`, 43.4 MB zipped; roughly 0.6 GB unzipped):

| File | Rows | Notes |
| --- | --- | --- |
| `agency.txt` | 1 | "Translink", timezone `Australia/Brisbane` |
| `routes.txt` | 553 | `route_type` counts: **3 (bus) 476, 2 (rail) 67, 4 (ferry) 9, 0 (tram) 1** |
| `trips.txt` | 173,183 | |
| `stops.txt` | 13,125 | `location_type` 0: 12,856 stops; 1: 269 stations |
| `stop_times.txt` | 4,668,624 | 261,740,251 bytes — the large file |
| `shapes.txt` | 1,163,355 | route geometry |
| `calendar.txt` / `calendar_dates.txt` | 208 / 193 | 29 service IDs applied on 2026-11-16 |
| `feed_info.txt` | 1 | publisher "Department of Transport and Main Roads - Translink Division"; **feed window 2026-11-14 to 2027-01-13** |

**Implications [V/A]:**
- The schedule has a rolling validity window, so ingestion must **detect new versions and reload**. How often TransLink republishes is **not established** (one data point: zip modified 2026-11-13).
- `stop_times.txt` is large. Loading it all into a small database or a serverless function is a design decision for M1, not a given.
- Times in `stop_times.txt` can exceed 24:00:00 (standard GTFS); parsers must handle that. **[A]** Not explicitly observed beyond the check in `coverage.py`, which parses `HH:MM:SS` with arbitrary hours.
- The Brisbane timezone has no daylight saving, which simplifies local-date handling. **[A]** General knowledge; the feed's `agency_timezone` is `Australia/Brisbane`.

## 5. GTFS-Realtime: what the feeds actually contain

### 5.1 Common **[V]**
- All three feeds: `gtfs_realtime_version = "2.0"`, `incrementality = FULL_DATASET` (full replacement, not diffs).
- **Update cadence in a 75-second sample, polled every ~4 s:** Vehicle Positions header timestamp changed 6 times (gaps of 20, 20, 10, 10, 10 s); Trip Updates 6 times (10, 10, 20, 20, 10 s); Alerts 4 times (20, 20, 20 s). So feeds refresh roughly every **10–20 seconds**, matching `max-age=10`. Polling faster than ~10 s gives no new data.
- Snapshot header age at decode time was ~43 s (this includes the time between download and analysis).

### 5.2 Vehicle Positions
- Fields present on **every** entity: `trip.trip_id`, `trip.route_id`, `position.latitude/longitude`, `current_status`, `timestamp`, `stop_id`, `vehicle.id`, `vehicle.label`. `current_stop_sequence` on 1,599 of 1,615.
- **Fields absent in this snapshot:** `bearing`, `speed`, `odometer`, `occupancy_status`, `congestion_level`, `trip.start_time`, `trip.start_date`, `trip.direction_id`. (**[V]** zero occurrences; **[A]** they may appear in other conditions.)
- 427 distinct `route_id`s; `schedule_relationship` is `SCHEDULED` for all; no duplicate vehicle IDs; `current_status`: 548 `STOPPED_AT`, 1,067 `IN_TRANSIT_TO`.
- Bounding box: latitude −28.174 to −26.343, longitude 152.334 to 153.543 (consistent with SEQ).
- **Mode breakdown via join to `routes.txt`:** bus 1,486, rail 88, ferry 25, tram 16 vehicles.
- **Staleness is real.** `feed header timestamp − vehicle timestamp`: min 1 s, median 21 s, **max 9,157 s (≈2.5 h)**. Share older than 60 s: 4.3 % (70 vehicles); >120 s: 3.7 %; >300 s: 2.7 %; >600 s: 1.9 %; >1,800 s: 0.9 % (14 vehicles). A "last seen" position is therefore sometimes hours old while still present in a fresh feed. This is exactly the case Master Plan §4.5 ("never present stale information as live") anticipates.

### 5.3 Trip Updates
- Entity fields: `trip` (with `trip_id`, `route_id`, `start_time`, `start_date`, `schedule_relationship`), `stop_time_update`, `timestamp` on all 2,503; `vehicle` on 2,431.
- **No trip-level `delay` field** on any entity (0 of 2,503). Delay exists only inside `stop_time_update.arrival/departure.delay`. Any "trip delay" must be derived (e.g. delay at the next upcoming stop).
- Stop-level **`delay` is present on every arrival/departure event** (85,770 events); no event had `time` only.
- 44,130 stop-time updates; per trip: min 1, median 14, max 81.
- `trip.schedule_relationship`: 2,433 `SCHEDULED` and **70 `REPLACEMENT` (value 5)**; zero `CANCELED`. Stop-level: 44,128 `SCHEDULED`, 2 `ADDED`. **[A]** The business meaning of the 70 `REPLACEMENT` trips (probably rail/bus replacement) was not investigated.
- `uncertainty: 30` appears in the sample entity; its distribution was not analysed.
- **Predictions are consistent with the static timetable [V]:** for 85,008 matched events, `(predicted time − delay) − scheduled seconds-since-midnight` was exactly 0 for 99.8 % and within ±60 s for 100 %. So `delay` is "predicted minus scheduled" against the **published GTFS**, and the static feed in use matches the real-time feed's baseline. (728 events had no matching scheduled stop-time.)
- Delay distribution over all events (seconds): min −6,588, p10 −154, **median 45**, p90 320, max 4,883; 31.6 % negative (early), 11.1 % ≥ 300 s.
- **Outliers exist:** −6,588 s (≈ 110 min early) and +4,883 s (≈ 81 min late) show the feed can contain extreme or erroneous predictions. **[A]** Cause unknown. Any metric must handle outliers explicitly (cap, flag, or exclude with disclosure).
- **Future trips are included.** 2,503 trips are in the feed versus 1,243 scheduled trips actually in progress; 1,349 TU trips have a scheduled span that does not include "now". **[A hypothesis, not measured]** Trips not yet started probably carry zero or placeholder delays; including them would bias delay statistics toward zero. Needs testing before any delay metric is defined.
- `entity.timestamp` age relative to header: median 29 s, max **19,394 s (≈5.4 h)**.

### 5.4 Service Alerts
- 66 alerts; all have `active_period`, `informed_entity`, `cause`, `effect`, `url`, `header_text`, `description_text`; text language `en-AU` only.
- `informed_entity` uses only **`route_id`** (296 references, 121 distinct routes, all present in `routes.txt`) and **`stop_id`** (77 references, 75 distinct; 1 not present in `stops.txt`). No trip- or agency-level targeting.
- `active_period`: multiple discrete windows per alert (some with start/end days apart). **45 of 66 alerts were "active now"** by their periods, so naive counting of all entities would overstate active alerts by ~47 %.
- **Cause counts:** Construction 33, Maintenance 19, Other 12, Technical problem 1, Demonstration 1.
  **Effect counts:** Stop moved 30, Reduced service 17, Accessibility issue 9, Modified service 5, Significant delays 2, No effect 2, Additional service 1.
  → At this snapshot, the alert feed is dominated by **planned works and stop changes**, not incident-driven disruptions. "Disruption statistics" will mostly reflect planned work unless alerts are categorised carefully.

## 6. Joining real-time to static **[V]**

| Join | Matched |
| --- | --- |
| VehiclePositions `route_id` → `routes.txt` | 1,615 / 1,615 |
| VehiclePositions `trip_id` → `trips.txt` | 1,615 / 1,615 |
| VehiclePositions `stop_id` → `stops.txt` | 1,615 / 1,615 |
| TripUpdates `route_id` / `trip_id` | 2,503 / 2,503 each |
| TripUpdates stop-time-update `stop_id` | 44,130 / 44,130 |
| Alerts `route_id` | all 121 distinct IDs matched |
| Alerts `stop_id` | 74 of 75 matched |
| Trips in both VP and TU | 1,610 of 1,610 VP trips |

This was measured against the static zip downloaded about a minute after the real-time snapshot (the zip's `Last-Modified` was 2026-11-13 19:45 UTC, so it had been published about two days earlier). A mismatch can still appear around the moment TransLink replaces the static file; ingestion must pair feed and schedule versions. That moment was not observed.

## 7. Coverage observed in the snapshot **[V]**

Scheduled trips in progress at the snapshot time (from `calendar`, `calendar_dates`, `stop_times`) versus real-time presence:

| Mode | Scheduled in progress | With a TripUpdate | With a VehiclePosition |
| --- | --- | --- | --- |
| All | 1,243 | 1,153 (92.8 %) | 1,137 (91.5 %) |
| Bus | 1,138 | 1,049 | 1,033 |
| Rail | 70 | 70 | 70 |
| Ferry | 19 | 18 | 18 |
| Tram | 16 | 16 | 16 |

Interpretation: at this single moment, roughly 7–9 % of scheduled in-progress trips had no real-time record, mostly buses. **This is not a claim about the whole network or all times.** The feed also describes 1,615 vehicles versus 1,243 scheduled in-progress trips; vehicles on layover or about to start explain part of that **[A]**.

Master Plan §4.5 forbids claiming full network coverage without evidence; this table is the evidence that coverage is *high but not complete*. TransLink's own T&C disclaim accuracy, reliability and completeness (§8).

## 8. Licence, terms and attribution

**[D][V — read on the TransLink page]**
- **CC BY 4.0**: attribution required. The T&C text read did not specify an exact attribution string. **[A]** Use "Contains data © State of Queensland (Translink), licensed under CC BY 4.0" style wording and confirm with TransLink; this wording is a proposal, not an official requirement.
- Data offered free; the State may change or remove data **without notice**. No service-level guarantee.
- **No warranty** on accuracy, reliability, completeness, currency or continuity; release and indemnity from users.
- **Do not imply State endorsement**; the application should carry a similar disclaimer for third-party users.
- **Translink name, logo and images:** approval required via `translink.opendata@tmr.qld.gov.au` (the T&C say to allow three business days). **Do not use the Translink logo or network images without approval.**
- **Contact details:** the T&C state that users "must provide (and keep current) your contact details to the State". **[A]** The practical mechanism (a registration form or email) was not found on the pages read. Ask the owner whether this has been done.
- Rate limits: none documented on the pages read; no throttling or error responses were observed in roughly 80 requests over a few minutes. **[A]** The real limit, if any, is unknown. The `max-age=10` header implies at most one useful fetch per 10 s per feed.

## 9. Other data mentioned but **not** investigated
- **Translink PT Performance Dashboard** (linked from the CKAN notes: https://translink.com.au/about-translink/reports-and-publications/performance) is described as providing visual performance data including on-time running. Whether that data is downloadable was **not** checked. It could provide official on-time-running context for validating any BrisPulse reliability proxy.
- Brisbane City Council Wi-Fi probe data, venue gate-egress data (original concept): not investigated, no evidence of availability.
- Weather, road traffic and other supporting sources: not investigated (Master Plan allows them only "if justified").

## 10. Verified data-quality hazards (feed to validation design)

| # | Hazard | Evidence |
| --- | --- | --- |
| H1 | Stale vehicle positions present in a fresh feed | Max age 9,157 s |
| H2 | Stale TripUpdate entity timestamps | Max age 19,394 s |
| H3 | Extreme delay values | −6,588 s … +4,883 s |
| H4 | Future / not-started trips in TripUpdates | 1,349 TU trips outside their scheduled window |
| H5 | Real-time records missing for some in-progress trips | 91.5 % VP / 92.8 % TU coverage |
| H6 | Multi-window alerts, planned works dominate | 45 of 66 active; 52 of 66 construction/maintenance |
| H7 | Alert references an unknown stop | 1 of 75 stop IDs |
| H8 | Schedule window rolls over | feed window 2026-11-14 → 2027-01-13 |
| H9 | Catalogue metadata wrong | CKAN sizes/formats/dates |
| H10 | Missing fields: no occupancy, bearing, speed | zero occurrences |

## 11. Unresolved questions

| ID | Question |
| --- | --- |
| D1 | How often is the static zip republished, and is the previous version retained? (Observe over weeks.) |
| D2 | How do feed contents behave overnight, on weekends, and during disruptions or events? |
| D3 | What are the 70 `REPLACEMENT` trips, and how are cancellations represented in practice (none observed)? |
| D4 | Does the feed ever go down or return errors, and what do outages look like? (No failure observed.) |
| D5 | Is there an actual rate limit or an optional API key (`vary: X-Api-Key`)? |
| D6 | What exact attribution wording and contact-registration steps does TransLink expect? |
| D7 | Why do predictions of −110 min / +81 min occur? |
| D8 | Is the PT Performance Dashboard data accessible for validation? |

## 12. Reproducing these findings

Probe scripts are in [`discovery/probes/`](discovery/probes/). They need Python with `gtfs-realtime-bindings` (this session used v3.0.0 with protobuf 7.36.2 in a throwaway virtualenv) and `curl`. Run them with Python's isolated mode (`python -I`).

| Script | Purpose |
| --- | --- |
| `analyze_rt.py <dir>` | Decode saved `VehiclePositions.pb`, `TripUpdates.pb`, `Alerts.pb` and print field presence, staleness, delay and alert statistics |
| `join_check.py <static_dir> <rt_dir>` | Join RT IDs to static files, mode breakdown, enum names |
| `coverage.py <static_dir> <rt_dir>` | Scheduled-in-progress vs real-time coverage and delay/schedule consistency |
| `cadence.py` | Poll the three feeds for ~75 s and report header-timestamp changes |

Feeds were saved with `curl -o <Feed>.pb https://gtfsrt.api.translink.com.au/api/realtime/SEQ/<Feed>`; the static zip with `curl -o SEQ_GTFS.zip https://gtfsrt.api.translink.com.au/GTFS/SEQ_GTFS.zip` and unzipped into its own empty directory. **No raw data files were committed** (size, and they are reproducible).
