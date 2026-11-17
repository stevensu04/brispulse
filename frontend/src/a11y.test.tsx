/**
 * Automated accessibility checks on every screen, with axe-core.
 *
 * jsdom has no layout, so colour contrast cannot be checked here; it was checked in a real
 * browser with axe in both themes and at phone width (see the roadmap, M5). These tests
 * guard everything structural: names, roles, labels, heading order, landmarks.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const feed = { state: "live", source_timestamp: "2026-11-17T09:00:00+10:00", fetched_at: "2026-11-17T09:00:05+10:00", age_seconds: 10, anomaly: false };
const meta = { generated_at: "2026-11-17T09:00:10+10:00", feeds: { vehicle_positions: feed, trip_updates: feed, alerts: feed }, static_version: null, notes: [] };
const route = { route_id: "R1", short_name: "100", long_name: "City Loop", mode: "bus" };
const delay = { sample_size: 6, excluded_implausible: 0, without_delay: 0, median_s: 60, p90_s: 400, early: 1, within_band: 4, late: 1 };
const alert = {
  alert_id: "A1", cause: "construction", effect: "stop_moved", planned_works: true, active: true,
  header: "Stop moved", description: "Use the temporary stop.", url: null,
  active_periods: [{ start: "2026-11-17T08:00:00+10:00", end: "2026-11-17T18:00:00+10:00" }],
  routes: [route], stops: [{ stop_id: "S1", name: "First Street" }],
};

const API: Record<string, unknown> = {
  "/status": {
    data: {
      feeds: Object.fromEntries(["vehicle_positions", "trip_updates", "alerts"].map((k) => [k, { ...feed, entity_count: 10, accepted: 10, rejected: {}, unmatched: 0, dropped_stale: 0, last_attempt_at: null, last_attempt_outcome: "ok" }])),
      static: { version_id: 1, published_at: null, feed_start_date: "2026-11-14", feed_end_date: "2027-01-13", routes: 1, stops: 1, trips: 1 },
      poll_interval_seconds: { vehicle_positions: 30, trip_updates: 60, alerts: 120 },
      history_enabled: false,
    },
    meta,
  },
  "/overview": {
    data: {
      vehicles: { fresh: 10, last_seen: 1, fresh_by_mode: { bus: 10 } },
      trips: { running: 6, running_by_mode: { bus: 6 }, canceled: 0, delay, delay_by_mode: { bus: delay } },
      alerts: { in_feed: 1, active: 1, active_planned_works: 1, active_other: 0 },
      coverage: null,
    },
    meta,
  },
  "/analytics/now": {
    data: {
      delays: { trips_counted: 6, routes_with_running_trips: 1, routes_with_late_trips: 1, late_routes: [{ route, running: 6, late: 1, early: 1, worst_delay_s: 400 }] },
      alerts: { active: 1, by_effect: { stop_moved: 1 }, by_cause: { construction: 1 }, routes_most_affected: [{ route, active_alerts: 1 }] },
    },
    meta,
  },
  "/routes": { data: [{ ...route, color: null, text_color: null, vehicles_fresh: 3, trips_running: 2, alerts_active: 1 }], meta },
  "/routes/R1": {
    data: {
      route: { ...route, color: null, text_color: null, vehicles_fresh: 3, trips_running: 1, alerts_active: 1 },
      vehicles: [],
      running_trips: [{ trip_id: "T1", headsign: "City", relationship: "scheduled", scheduled_start: "2026-11-17T08:30:00+10:00", vehicle_id: "V1", predicted_delay_s: 400, delay_implausible: false, next_stop: { stop_id: "S1", name: "First Street" } }],
      alerts: [alert],
    },
    meta,
  },
  "/alerts": { data: [alert], meta },
  "/meta/metrics": {
    data: {
      metrics: [{ name: "Fresh vehicles", definition: "d", source: "s", limitations: "l" }],
      thresholds: { delay_early_s: 60, delay_late_s: 300 },
      freshness_limits_seconds: {},
      attribution: "Contains Translink data.",
      disclaimer: "Independent.",
    },
    meta,
  },
};

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

async function violationsOn(hash: string, heading: RegExp) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const body = API[url.replace("/api/v1", "")];
      return body
        ? new Response(JSON.stringify(body))
        : new Response(JSON.stringify({ error: { code: "not_found", message: "no" } }), { status: 404 });
    }),
  );
  window.location.hash = hash;
  const { container } = render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  );
  await screen.findByRole("heading", { level: 1, name: heading });
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  return result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

describe("accessibility", () => {
  it.each([
    ["#/", /right now/],
    ["#/routes", /Routes/],
    ["#/routes/R1", /City Loop/],
    ["#/alerts", /Service alerts/],
    ["#/about", /About this data/],
  ])("%s has no axe violations", async (hash, heading) => {
    expect(await violationsOn(hash, heading)).toEqual([]);
  });
});
