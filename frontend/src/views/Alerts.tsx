import { useState } from "react";
import type { Alert } from "../api/client";
import { useAlerts } from "../api/hooks";
import { FreshnessLine } from "../components/Freshness";
import { Empty, Notes, QueryView } from "../components/States";
import { formatDayAndClock, sentenceCase } from "../lib/format";
import { href } from "../lib/router";

function periodText(alert: Alert): string {
  const now = Date.now();
  const current = alert.active_periods.find(
    (p) => (!p.start || Date.parse(p.start) <= now) && (!p.end || now <= Date.parse(p.end)),
  );
  if (current) return current.end ? `Until ${formatDayAndClock(current.end)}` : "No end time given";
  const next = alert.active_periods
    .filter((p) => p.start && Date.parse(p.start) > now)
    .sort((a, b) => Date.parse(a.start ?? "") - Date.parse(b.start ?? ""))[0];
  if (next) return `Starts ${formatDayAndClock(next.start)}`;
  return alert.active_periods.length === 0 ? "No period given" : "Ended";
}

/** `headingLevel` keeps the page outline in order: 2 on the alerts page, 3 under a route's section. */
export function AlertCard({ alert, headingLevel = 2 }: { alert: Alert; headingLevel?: 2 | 3 }) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <article className="card stack" style={{ gap: 8 }}>
      <div className="row">
        <span className="chip">{alert.active ? "Active now" : "Not active now"}</span>
        <span className="chip">{sentenceCase(alert.effect)}</span>
        <span className="chip">{alert.planned_works ? "Planned works" : sentenceCase(alert.cause)}</span>
      </div>
      <Heading className="card-title">{alert.header ?? "Service alert"}</Heading>
      <p className="small secondary">{periodText(alert)}</p>
      {alert.description ? <p className="small">{alert.description}</p> : null}
      {alert.routes.length > 0 ? (
        <p className="row small">
          <span className="secondary">Routes:</span>
          {alert.routes.slice(0, 12).map((route) => (
            <a key={route.route_id} className="chip" href={href("routes", route.route_id)}>
              {route.short_name ?? route.route_id}
            </a>
          ))}
          {alert.routes.length > 12 ? <span className="muted">and {alert.routes.length - 12} more</span> : null}
        </p>
      ) : null}
      {alert.stops.length > 0 ? (
        <p className="small secondary">
          Stops: {alert.stops.slice(0, 4).map((stop) => stop.name ?? `stop ${stop.stop_id}`).join("; ")}
          {alert.stops.length > 4 ? ` and ${alert.stops.length - 4} more` : ""}
        </p>
      ) : null}
      {alert.url ? (
        <p className="small">
          <a href={alert.url} target="_blank" rel="noreferrer">
            Details on the TransLink website
          </a>
        </p>
      ) : null}
    </article>
  );
}

export function Alerts() {
  const query = useAlerts();
  const [activeOnly, setActiveOnly] = useState(true);
  return (
    <div className="stack">
      <header>
        <h1 className="page-title">Service alerts</h1>
        <p className="page-lead">Notices TransLink has published about routes and stops.</p>
      </header>
      <QueryView query={query} what="Alerts">
        {(alerts, notes) => {
          const shown = activeOnly ? alerts.filter((alert) => alert.active) : alerts;
          return (
            <>
              {query.data ? <FreshnessLine meta={query.data.meta} /> : null}
              <Notes notes={notes} />
              <div className="row" role="group" aria-label="Which alerts to show">
                <button type="button" className="chip chip-button" aria-pressed={activeOnly} onClick={() => setActiveOnly(true)}>
                  Active now ({alerts.filter((alert) => alert.active).length})
                </button>
                <button type="button" className="chip chip-button" aria-pressed={!activeOnly} onClick={() => setActiveOnly(false)}>
                  All in the feed ({alerts.length})
                </button>
              </div>
              <p className="small muted">
                An alert not marked as planned works is not necessarily an incident: TransLink files
                timetable changes and general notices under other causes.
              </p>
              {shown.length === 0 ? (
                <Empty>No alerts are active right now.</Empty>
              ) : (
                shown.map((alert) => <AlertCard key={alert.alert_id} alert={alert} />)
              )}
            </>
          );
        }}
      </QueryView>
    </div>
  );
}
