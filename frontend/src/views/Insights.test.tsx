import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Insights } from "./Insights";

const meta = { generated_at: "2026-11-17T09:00:00+10:00", feeds: {}, static_version: null, notes: [] };
const route = (id: string, short: string, name: string) => ({ route_id: id, short_name: short, long_name: name, mode: "bus" });

function serve(analytics: unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url.endsWith("/analytics/now")
        ? new Response(JSON.stringify(analytics), { status })
        : new Response(JSON.stringify({ error: { code: "not_ready", message: "starting" } }), { status: 503 }),
    ),
  );
}

function show() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <Insights />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("Insights", () => {
  it("lists the routes with the most late trips, linking to each route", async () => {
    serve({
      data: {
        delays: {
          trips_counted: 780,
          routes_with_running_trips: 310,
          routes_with_late_trips: 64,
          late_routes: [
            { route: route("444-4", "444", "Moggill - City"), running: 9, late: 4, early: 0, worst_delay_s: 1260 },
            { route: route("60-4", "60", "West End - Teneriffe"), running: 15, late: 3, early: 2, worst_delay_s: 540 },
          ],
        },
        alerts: null,
      },
      meta,
    });

    show();

    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(within(rows[1]!).getByRole("link").getAttribute("href")).toBe("#/routes/444-4");
    expect(within(rows[1]!).getByText("21 min late")).toBeTruthy();
    expect(screen.getByText("64 of 310 routes with running trips have at least one late trip.")).toBeTruthy();
  });

  it("says so when no trip is late, instead of showing an empty table", async () => {
    serve({
      data: { delays: { trips_counted: 12, routes_with_running_trips: 5, routes_with_late_trips: 0, late_routes: [] }, alerts: null },
      meta,
    });

    show();

    expect(await screen.findByText(/No running trip is predicted to be more than 5 minutes late/)).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows alert counts by effect as numbers, not only as bars", async () => {
    serve({
      data: {
        delays: null,
        alerts: {
          active: 45,
          by_effect: { reduced_service: 20, stop_moved: 18, significant_delays: 7 },
          by_cause: { construction: 21, other_cause: 24 },
          routes_most_affected: [{ route: route("BNSH-5", "BNSH", "Northern Line"), active_alerts: 6 }],
        },
      },
      meta,
    });

    show();

    const list = await screen.findByRole("list", { name: "Active alerts by effect" });
    const items = within(list).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual(["Reduced service20", "Stop moved18", "Significant delays7"]);
    expect(screen.getByRole("link", { name: "BNSH" }).getAttribute("href")).toBe("#/routes/BNSH-5");
  });

  it("explains withheld sections in the API's words", async () => {
    serve({
      data: null,
      meta: { ...meta, notes: ["vehicle_positions: the latest data is 901 s old, beyond the 900 s limit, so its values are withheld as null."] },
    });

    show();

    expect(await screen.findByRole("heading", { name: "Insights unavailable" })).toBeTruthy();
    expect(screen.getByText(/withheld as null/)).toBeTruthy();
  });
});
