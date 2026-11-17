import type { AnalyticsNow } from "../api/client";
import { useAnalytics } from "../api/hooks";
import { DelayText } from "../components/Delay";
import { Notes, QueryView } from "../components/States";
import { type BandLimits, formatCount, sentenceCase } from "../lib/format";
import { href } from "../lib/router";
import { useBandLimits } from "../lib/useBandLimits";

/**
 * A count shown as a bar and a number. The bar is one neutral colour because it shows
 * one quantity; the number beside it carries the value, so nothing depends on colour.
 */
function CountBars({ items, label }: { items: [string, number][]; label: string }) {
  const max = Math.max(1, ...items.map(([, count]) => count));
  return (
    <ul className="count-bars" aria-label={label}>
      {items.map(([name, count]) => (
        <li key={name}>
          <span className="count-name">{name}</span>
          <span className="count-track" aria-hidden="true">
            <span className="count-fill" style={{ width: `${(count / max) * 100}%` }} />
          </span>
          <span className="count-value figures">{formatCount(count)}</span>
        </li>
      ))}
    </ul>
  );
}

function LateRoutes({ data, limits }: { data: NonNullable<AnalyticsNow["delays"]>; limits: BandLimits }) {
  if (data.late_routes.length === 0) {
    return <p className="secondary">No running trip is predicted to be more than {Math.round(limits.lateSeconds / 60)} minutes late right now.</p>;
  }
  return (
    <>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Route</th>
              <th scope="col" className="num">Late</th>
              <th scope="col" className="num">Running</th>
              <th scope="col" className="num">Worst</th>
            </tr>
          </thead>
          <tbody>
            {data.late_routes.map((row) => (
              <tr key={row.route.route_id}>
                <th scope="row">
                  <a href={href("routes", row.route.route_id)}>
                    <span className="route-badge" style={{ marginRight: 8 }}>{row.route.short_name ?? "–"}</span>
                    {row.route.long_name ?? row.route.route_id}
                  </a>
                </th>
                <td className="num">{formatCount(row.late)}</td>
                <td className="num">{formatCount(row.running)}</td>
                <td className="num">
                  <DelayText seconds={row.worst_delay_s} limits={limits} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small muted" style={{ marginTop: 8 }}>
        {formatCount(data.routes_with_late_trips)} of {formatCount(data.routes_with_running_trips)} routes with running trips have at least one late trip.
      </p>
    </>
  );
}

/** Where the delays and the disruptions are, at this moment. */
export function Insights() {
  const query = useAnalytics();
  const limits = useBandLimits();
  return (
    <QueryView query={query} what="Insights">
      {(data, notes) => (
        <>
          {data.delays ? (
            <section className="card" aria-labelledby="late-routes">
              <h2 className="card-title" id="late-routes">
                Where the delays are now
              </h2>
              <p className="small secondary" style={{ margin: "4px 0 8px" }}>
                Routes with the most running trips predicted to be over {Math.round(limits.lateSeconds / 60)} minutes late.
              </p>
              <LateRoutes data={data.delays} limits={limits} />
            </section>
          ) : null}
          {data.alerts && data.alerts.active > 0 ? (
            <section className="card" aria-labelledby="alert-effects">
              <h2 className="card-title" id="alert-effects">
                Active alerts by effect
              </h2>
              <CountBars
                label="Active alerts by effect"
                items={Object.entries(data.alerts.by_effect).map(([effect, count]) => [sentenceCase(effect), count])}
              />
              {data.alerts.routes_most_affected.length > 0 ? (
                <p className="small secondary" style={{ marginTop: 10 }}>
                  Most named routes:{" "}
                  {data.alerts.routes_most_affected.slice(0, 5).map((row, index) => (
                    <span key={row.route.route_id}>
                      {index > 0 ? ", " : ""}
                      <a href={href("routes", row.route.route_id)}>{row.route.short_name ?? row.route.route_id}</a> ({row.active_alerts})
                    </span>
                  ))}
                </p>
              ) : null}
            </section>
          ) : null}
          <Notes notes={notes.filter((note) => !note.startsWith("Late means"))} />
        </>
      )}
    </QueryView>
  );
}
