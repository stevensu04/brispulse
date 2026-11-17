import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DelaySummary, Meta } from "../api/client";
import { DEFAULT_BANDS } from "../lib/format";
import { Overview } from "../views/Overview";
import { DelayBands, DelayText } from "./Delay";
import { FreshnessBadge, FreshnessLine, worstState } from "./Freshness";
import { Notes, Unavailable } from "./States";

const feed = (state: string, age: number | null) => ({
  state,
  age_seconds: age,
  source_timestamp: age === null ? null : "2026-11-16T09:03:20+10:00",
  fetched_at: age === null ? null : "2026-11-16T09:03:25+10:00",
  anomaly: false,
});

function meta(feeds: Record<string, unknown>, notes: string[] = []): Meta {
  return { generated_at: "2026-11-16T09:03:41+10:00", feeds, static_version: null, notes } as unknown as Meta;
}

const summary: DelaySummary = {
  sample_size: 1046,
  excluded_implausible: 3,
  without_delay: 0,
  median_s: 60,
  p90_s: 360,
  early: 112,
  within_band: 801,
  late: 133,
};

afterEach(() => vi.unstubAllGlobals());

describe("DelayBands", () => {
  it("names and counts every band in text, not only in colour", () => {
    render(<DelayBands summary={summary} limits={DEFAULT_BANDS} />);

    expect(screen.getByRole("img").getAttribute("aria-label")).toBe(
      "Of 1046 running trips: 112 early, 801 within band, 133 late.",
    );
    const legend = screen.getByRole("list");
    expect(within(legend).getByText("Early")).toBeTruthy();
    expect(within(legend).getByText("801 (77%)")).toBeTruthy();
    expect(within(legend).getByText("133 (13%)")).toBeTruthy();
    expect(within(legend).getByText("more than 5 min late")).toBeTruthy();
  });

  it("says so when there is nothing to show, instead of drawing an empty bar", () => {
    render(<DelayBands summary={{ ...summary, sample_size: 0, early: 0, within_band: 0, late: 0 }} limits={DEFAULT_BANDS} />);

    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByText("No running trips with a predicted delay right now.")).toBeTruthy();
  });
});

describe("DelayText", () => {
  it("writes the delay in words and marks its band", () => {
    render(<DelayText seconds={420} limits={DEFAULT_BANDS} />);

    const text = screen.getByText("7 min late");
    expect(text.getAttribute("data-band")).toBe("late");
  });

  it("does not invent a number when there is no prediction", () => {
    render(<DelayText seconds={null} limits={DEFAULT_BANDS} />);

    expect(screen.getByText("no prediction")).toBeTruthy();
  });
});

describe("freshness", () => {
  it("shows the state as a word", () => {
    render(<FreshnessBadge state="stale" />);

    expect(screen.getByText("Stale")).toBeTruthy();
  });

  it("reports the least fresh feed", () => {
    const feeds = meta({ vehicle_positions: feed("live", 10), alerts: feed("delayed", 700) }).feeds;

    expect(worstState(feeds)).toBe("delayed");
    expect(worstState({})).toBeNull();
  });

  it("quotes the vehicle feed's age, not the slower alerts feed's", () => {
    render(
      <FreshnessLine
        meta={meta({ vehicle_positions: feed("live", 14), trip_updates: feed("live", 44), alerts: feed("live", 118) })}
      />,
    );

    expect(screen.getByText(/Vehicle data from TransLink 14 s ago/)).toBeTruthy();
    expect(screen.getByText("Live")).toBeTruthy();
  });

  it("says when nothing has been received", () => {
    render(<FreshnessLine meta={meta({ vehicle_positions: feed("unavailable", null) })} />);

    expect(screen.getByText("No data received yet")).toBeTruthy();
    expect(screen.getByText("Unavailable")).toBeTruthy();
  });
});

describe("states", () => {
  it("explains withheld data in the API's own words", () => {
    render(<Unavailable what="Vehicle positions" notes={["vehicle_positions: the latest data is 901 s old."]} />);

    expect(screen.getByRole("heading", { name: "Vehicle positions unavailable" })).toBeTruthy();
    expect(screen.getByText("vehicle_positions: the latest data is 901 s old.")).toBeTruthy();
  });

  it("lists several notes and renders nothing for none", () => {
    const { container, rerender } = render(<Notes notes={["first", "second"]} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);

    rerender(<Notes notes={[]} />);
    expect(container.innerHTML).toBe("");
  });
});

function withQueries(ui: ReactNode) {
  // No retry override here: the hooks' own retry rules are part of what is tested.
  return <QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>;
}

function serve(routes: Record<string, { status?: number; body: unknown }>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const match = routes[url.replace("/api/v1", "")] ?? { status: 404, body: { error: { code: "not_found", message: "nope" } } };
      return new Response(JSON.stringify(match.body), { status: match.status ?? 200 });
    }),
  );
}

describe("Overview", () => {
  it("shows 'Unavailable' for values the API withheld, never a zero", async () => {
    serve({
      "/overview": {
        body: {
          data: { vehicles: null, trips: null, alerts: { in_feed: 3, active: 2, active_planned_works: 1, active_other: 1 }, coverage: null },
          meta: meta(
            { vehicle_positions: feed("unavailable", 2000), trip_updates: feed("unavailable", 2000), alerts: feed("live", 60) },
            ["vehicle_positions: the latest data is 2000 s old, beyond the 900 s limit, so its values are withheld as null."],
          ),
        },
      },
      "/meta/metrics": { status: 503, body: { error: { code: "not_ready", message: "starting" } } },
    });

    render(withQueries(<Overview />));

    const vehicles = (await screen.findByText("Vehicles reporting")).parentElement!;
    expect(within(vehicles).getByText("Unavailable")).toBeTruthy();
    expect(within(vehicles).queryByText("0")).toBeNull();
    const alerts = screen.getByText("Active alerts").parentElement!;
    expect(within(alerts).getByText("2")).toBeTruthy();
    expect(screen.getByText(/withheld as null/)).toBeTruthy();
    expect(screen.queryByText("Predicted delay of running trips")).toBeNull();
  });

  it("shows live figures with their caveat", async () => {
    serve({
      "/overview": {
        body: {
          data: {
            vehicles: { fresh: 1325, last_seen: 14, fresh_by_mode: { bus: 1197, rail: 95 } },
            trips: {
              running: 1046,
              running_by_mode: { bus: 933, rail: 85 },
              canceled: 0,
              delay: summary,
              delay_by_mode: { bus: summary, rail: { ...summary, sample_size: 4, median_s: null, p90_s: null } },
            },
            alerts: { in_feed: 60, active: 38, active_planned_works: 26, active_other: 12 },
            coverage: null,
          },
          meta: meta({ vehicle_positions: feed("live", 14), trip_updates: feed("live", 14), alerts: feed("live", 14) }),
        },
      },
      "/meta/metrics": { status: 503, body: { error: { code: "not_ready", message: "starting" } } },
    });

    render(withQueries(<Overview />));

    expect(await screen.findByText("1,325")).toBeTruthy();
    expect(screen.getByText("1 in 10 trips: 6 min late or worse")).toBeTruthy();
    expect(screen.getByText("3 trips left out: their predicted delay was over an hour, which is more likely a data fault than a real delay.")).toBeTruthy();
    // A mode with too few trips gets words, not a made-up median.
    expect(screen.getByText("too few trips")).toBeTruthy();
    expect(screen.getByText(/not measured arrivals and not on-time performance/)).toBeTruthy();
  });

  it("shows the waking-up screen while the server is starting", async () => {
    serve({ "/overview": { status: 503, body: { error: { code: "not_ready", message: "The service is starting." } } } });

    render(withQueries(<Overview />));

    expect(await screen.findByRole("heading", { name: "Waking up" })).toBeTruthy();
  });

  it("shows a real error with a way to retry", async () => {
    serve({ "/overview": { status: 500, body: { error: { code: "internal_error", message: "An unexpected error occurred." } } } });

    render(withQueries(<Overview />));

    expect(await screen.findByText("An unexpected error occurred.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });
});
