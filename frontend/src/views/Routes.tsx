import { ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import { useRoute, useRoutes } from "../api/hooks";
import { DelayText } from "../components/Delay";
import { FreshnessLine } from "../components/Freshness";
import { ModeFilter, ModeIcon } from "../components/Mode";
import { Empty, Notes, QueryView } from "../components/States";
import { formatClock, formatCount, modeLabel } from "../lib/format";
import { href } from "../lib/router";
import { useBandLimits } from "../lib/useBandLimits";
import { AlertCard } from "./Alerts";
import { TripPanel } from "./TripPanel";

const PAGE = 60;

export function Routes() {
  const query = useRoutes();
  const [mode, setMode] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [activeOnly, setActiveOnly] = useState(true);
  const [limit, setLimit] = useState(PAGE);
  return (
    <div className="stack">
      <header>
        <h1 className="page-title">Routes</h1>
        <p className="page-lead">Every route in the timetable, with what is running on it now.</p>
      </header>
      <QueryView query={query} what="Routes">
        {(routes, notes) => {
          const words = search.trim().toLowerCase();
          const liveKnown = routes.some((route) => route.vehicles_fresh !== null);
          const shown = routes.filter(
            (route) =>
              (mode === null || route.mode === mode) &&
              (!activeOnly || !liveKnown || (route.vehicles_fresh ?? 0) > 0) &&
              (words === "" ||
                `${route.short_name ?? ""} ${route.long_name ?? ""}`.toLowerCase().includes(words)),
          );
          return (
            <>
              {query.data ? <FreshnessLine meta={query.data.meta} /> : null}
              <Notes notes={notes} />
              <div className="stack" style={{ gap: 12 }}>
                <label className="field">
                  Find a route
                  <input
                    className="input"
                    type="search"
                    value={search}
                    placeholder="Number or name, for example 60 or Airport"
                    onChange={(event) => {
                      setSearch(event.target.value);
                      setLimit(PAGE);
                    }}
                  />
                </label>
                <ModeFilter value={mode} onChange={setMode} />
                <div className="row" role="group" aria-label="Which routes to show">
                  <button type="button" className="chip chip-button" aria-pressed={activeOnly} onClick={() => setActiveOnly(true)}>
                    With vehicles now
                  </button>
                  <button type="button" className="chip chip-button" aria-pressed={!activeOnly} onClick={() => setActiveOnly(false)}>
                    All routes
                  </button>
                </div>
              </div>
              <p className="small muted figures" aria-live="polite">
                {formatCount(shown.length)} of {formatCount(routes.length)} routes
              </p>
              {shown.length === 0 ? (
                <Empty>No routes match. Try another name, or show all routes.</Empty>
              ) : (
                <ul className="list card" style={{ padding: 0 }}>
                  {shown.slice(0, limit).map((route) => (
                    <li key={route.route_id}>
                      <a className="list-item" href={href("routes", route.route_id)}>
                        <span className="route-badge">{route.short_name ?? "–"}</span>
                        <span className="grow">
                          <span className="truncate" style={{ display: "block", fontWeight: 600 }}>
                            {route.long_name ?? route.route_id}
                          </span>
                          <span className="small secondary row" style={{ gap: 6 }}>
                            <ModeIcon mode={route.mode} size={14} />
                            {modeLabel(route.mode)}
                            {" · "}
                            {route.vehicles_fresh === null
                              ? "live data unavailable"
                              : `${route.vehicles_fresh} vehicle${route.vehicles_fresh === 1 ? "" : "s"}`}
                            {route.alerts_active ? ` · ${route.alerts_active} alert${route.alerts_active === 1 ? "" : "s"}` : ""}
                          </span>
                        </span>
                        <ChevronRight size={18} aria-hidden="true" />
                      </a>
                    </li>
                  ))}
                </ul>
              )}
              {shown.length > limit ? (
                <button type="button" className="button" onClick={() => setLimit(limit + PAGE)}>
                  Show more routes
                </button>
              ) : null}
            </>
          );
        }}
      </QueryView>
    </div>
  );
}

export function RouteDetail({ routeId }: { routeId: string }) {
  const query = useRoute(routeId);
  const limits = useBandLimits();
  const [tripId, setTripId] = useState<string | null>(null);
  const trips = query.data?.data?.running_trips;
  const sorted = useMemo(
    () => [...(trips ?? [])].sort((a, b) => (b.predicted_delay_s ?? -Infinity) - (a.predicted_delay_s ?? -Infinity)),
    [trips],
  );
  return (
    <div className="stack">
      <p>
        <a href={href("routes")}>All routes</a>
      </p>
      <QueryView query={query} what="Route">
        {(detail, notes) => (
          <>
            <header>
              <h1 className="page-title row">
                <span className="route-badge">{detail.route.short_name ?? "–"}</span>
                {detail.route.long_name ?? detail.route.route_id}
              </h1>
              <p className="page-lead row" style={{ gap: 6 }}>
                <ModeIcon mode={detail.route.mode} />
                {modeLabel(detail.route.mode)}
              </p>
            </header>
            {query.data ? <FreshnessLine meta={query.data.meta} /> : null}
            <Notes notes={notes} />

            <section className="card" aria-labelledby="running">
              <h2 className="card-title" id="running">
                Running now
              </h2>
              {detail.running_trips === null ? (
                <p className="secondary" style={{ marginTop: 8 }}>
                  Unavailable: this needs both vehicle positions and trip updates.
                </p>
              ) : sorted.length === 0 ? (
                <p className="secondary" style={{ marginTop: 8 }}>
                  No trips on this route are running right now.
                </p>
              ) : (
                <ul className="list" style={{ marginTop: 8 }}>
                  {sorted.map((trip) => (
                    <li key={trip.trip_id}>
                      <button
                        type="button"
                        className="list-item"
                        aria-expanded={tripId === trip.trip_id}
                        onClick={() => setTripId(tripId === trip.trip_id ? null : trip.trip_id)}
                      >
                        <span className="grow">
                          <span style={{ display: "block", fontWeight: 600 }}>
                            To {trip.headsign ?? "unknown destination"}
                          </span>
                          <span className="small secondary">
                            Started {formatClock(trip.scheduled_start)}
                            {trip.next_stop?.name ? ` · next: ${trip.next_stop.name}` : ""}
                          </span>
                        </span>
                        <DelayText seconds={trip.predicted_delay_s} limits={limits} />
                      </button>
                      {tripId === trip.trip_id ? (
                        <div style={{ padding: "8px 12px 16px" }}>
                          <TripPanel tripId={trip.trip_id} showTitle={false} />
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="stack" aria-labelledby="route-alerts">
              <h2 className="card-title" id="route-alerts">
                Alerts for this route
              </h2>
              {detail.alerts === null ? (
                <p className="secondary">Alerts are unavailable right now.</p>
              ) : detail.alerts.length === 0 ? (
                <p className="secondary">No alerts for this route.</p>
              ) : (
                detail.alerts.map((alert) => <AlertCard key={alert.alert_id} alert={alert} />)
              )}
            </section>
          </>
        )}
      </QueryView>
    </div>
  );
}
