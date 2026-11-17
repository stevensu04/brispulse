# Test fixtures

## `translink_2026-11-16_0903/`

A small sample cut from the real TransLink South East Queensland GTFS-Realtime feeds
as published on Monday 16 November 2026 at 09:03 (Brisbane time):

- `vehicle_positions.pb`, `trip_updates.pb`: about 130 trips chosen to cover the cases
  the collector must handle (running trips, trips not yet started, stale vehicles, a
  cancelled trip, replacement trips, trips with two vehicle records).
- `alerts.pb`: every alert in the feed at that moment.
- `reference.json`: the static GTFS IDs (routes with their mode, trips, stops) that
  these records refer to, so they can be validated without the full schedule.

The sample was produced by `discovery/probes/make_test_fixture.py`. It is test data
frozen at one moment and says nothing about current services.

**Attribution.** Contains Translink data © State of Queensland (Department of Transport
and Main Roads), licensed under
[Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/).
Source: <https://translink.com.au/about-translink/open-data>. The data has been reduced
to a sample; no values were altered.
