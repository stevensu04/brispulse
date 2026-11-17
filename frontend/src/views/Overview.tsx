import type { OverviewData } from "../api/client";
import { useOverview } from "../api/hooks";
import { DelayBands } from "../components/Delay";
import { FreshnessLine } from "../components/Freshness";
import { ModeLabel } from "../components/Mode";
import { Notes, QueryView } from "../components/States";
import { type BandLimits, MODE_ORDER, formatCount, formatDelay } from "../lib/format";
import { href } from "../lib/router";
import { useBandLimits } from "../lib/useBandLimits";
import { Insights } from "./Insights";
import { TableScroll } from "../components/TableScroll";

/** A headline number. When the value cannot be given it says so; it never shows 0. */
function Tile({ label, value, detail }: { label: string; value: string | null; detail?: string }) {
  return (
    <div className="card">
      <div className="tile-label">{label}</div>
      {value === null ? (
        <div className="tile-value is-missing">Unavailable</div>
      ) : (
        <div className="tile-value figures">{value}</div>
      )}
      {detail ? <div className="tile-detail">{detail}</div> : null}
    </div>
  );
}

function ByMode({ data, limits }: { data: OverviewData; limits: BandLimits }) {
  const modes = MODE_ORDER.filter(
    (mode) => data.vehicles?.fresh_by_mode[mode] !== undefined || data.trips?.running_by_mode[mode] !== undefined,
  );
  if (modes.length === 0) return null;
  return (
    <section className="card" aria-labelledby="by-mode">
      <h2 className="card-title" id="by-mode">
        By mode
      </h2>
      <TableScroll label="Figures by mode">
        <table>
          <thead>
            <tr>
              <th scope="col">Mode</th>
              <th scope="col" className="num">Vehicles</th>
              <th scope="col" className="num">Running trips</th>
              <th scope="col" className="num">Median delay</th>
              <th scope="col" className="num">Late</th>
            </tr>
          </thead>
          <tbody>
            {modes.map((mode) => {
              const delay = data.trips?.delay_by_mode[mode];
              return (
                <tr key={mode}>
                  <th scope="row">
                    <ModeLabel mode={mode} />
                  </th>
                  <td className="num">{data.vehicles ? formatCount(data.vehicles.fresh_by_mode[mode] ?? 0) : "–"}</td>
                  <td className="num">{data.trips ? formatCount(data.trips.running_by_mode[mode] ?? 0) : "–"}</td>
                  <td className="num">
                    {delay?.median_s != null ? formatDelay(delay.median_s) : <span className="muted">too few trips</span>}
                  </td>
                  <td className="num">
                    {delay ? `${formatCount(delay.late)} of ${formatCount(delay.sample_size)}` : "–"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </TableScroll>
      <p className="small muted" style={{ marginTop: 8 }}>
        Late means predicted more than {Math.round(limits.lateSeconds / 60)} minutes late at the next stop.
      </p>
    </section>
  );
}

export function Overview() {
  const query = useOverview();
  const limits = useBandLimits();
  return (
    <div className="stack">
      <header>
        <h1 className="page-title">South East Queensland, right now</h1>
        <p className="page-lead">
          Public transport as TransLink is reporting it at this moment. This dashboard shows the
          present only: it keeps no history.
        </p>
      </header>
      <QueryView query={query} what="Overview">
        {(data, notes) => {
          const delay = data.trips?.delay;
          return (
            <>
              {query.data ? <FreshnessLine meta={query.data.meta} /> : null}
              <div className="grid-tiles">
                <Tile
                  label="Vehicles reporting"
                  value={data.vehicles ? formatCount(data.vehicles.fresh) : null}
                  detail={
                    data.vehicles
                      ? `${formatCount(data.vehicles.last_seen)} more last seen over 90 s ago`
                      : undefined
                  }
                />
                <Tile
                  label="Trips running"
                  value={data.trips ? formatCount(data.trips.running) : null}
                  detail={data.trips ? `${formatCount(data.trips.canceled)} cancelled in the feed` : undefined}
                />
                <Tile
                  label="Median predicted delay"
                  value={delay ? (delay.median_s != null ? formatDelay(delay.median_s) : "Too few trips") : null}
                  detail={
                    delay?.p90_s != null ? `1 in 10 trips: ${formatDelay(delay.p90_s)} or worse` : undefined
                  }
                />
                <Tile
                  label="Active alerts"
                  value={data.alerts ? formatCount(data.alerts.active) : null}
                  detail={
                    data.alerts
                      ? `${formatCount(data.alerts.active_planned_works)} planned works, ${formatCount(data.alerts.active_other)} other`
                      : undefined
                  }
                />
              </div>

              {delay ? (
                <section className="card" aria-labelledby="bands">
                  <div className="row spread">
                    <h2 className="card-title" id="bands">
                      Predicted delay of running trips
                    </h2>
                    <span className="small muted figures">{formatCount(delay.sample_size)} trips</span>
                  </div>
                  <DelayBands summary={delay} limits={limits} />
                  {delay.excluded_implausible > 0 ? (
                    <p className="small muted" style={{ marginTop: 10 }}>
                      {formatCount(delay.excluded_implausible)} trips left out: their predicted delay was over an hour, which is more likely a data fault than a real delay.
                    </p>
                  ) : null}
                </section>
              ) : null}

              <ByMode data={data} limits={limits} />

              <Insights />

              <Notes
                tone="info"
                notes={[
                  "Delays are TransLink's predictions for each trip's next stop. They are not measured arrivals and not on-time performance.",
                ]}
              />
              <Notes notes={notes.filter((note) => !note.startsWith("Delay figures") && !note.startsWith("coverage:"))} />
              <p className="row">
                <a className="button" href={href("map")}>Open the live map</a>
                <a className="button" href={href("about")}>What these numbers mean</a>
              </p>
            </>
          );
        }}
      </QueryView>
    </div>
  );
}
