import { useMetrics, useStatus } from "../api/hooks";
import { FreshnessBadge } from "../components/Freshness";
import { QueryView } from "../components/States";
import { formatClock, formatDuration, sentenceCase } from "../lib/format";
import { TableScroll } from "../components/TableScroll";

export function About() {
  const metrics = useMetrics();
  const status = useStatus();
  const feeds = status.data?.data?.feeds;
  const schedule = status.data?.data?.static;
  return (
    <div className="stack">
      <header>
        <h1 className="page-title">About this data</h1>
        <p className="page-lead">
          Where the numbers come from, what they mean, and what they cannot tell you.
        </p>
      </header>

      <section className="card stack" style={{ gap: 8 }}>
        <h2 className="card-title">What BrisPulse is</h2>
        <p>
          A live view of public transport in South East Queensland, built from the real-time feeds
          TransLink publishes as open data. It shows the present moment only. Nothing is stored, so
          there are no trends or history here.
        </p>
        <p>
          The server sleeps when nobody is using it and wakes on a visit, which is why the first
          page can take a moment to appear.
        </p>
      </section>

      {feeds ? (
        <section className="card" aria-labelledby="feeds">
          <h2 className="card-title" id="feeds">
            Data feeds right now
          </h2>
          <TableScroll label="Data feeds right now">
            <table>
              <thead>
                <tr>
                  <th scope="col">Feed</th>
                  <th scope="col">State</th>
                  <th scope="col">Data from</th>
                  <th scope="col" className="num">Records</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(feeds).map(([name, feed]) => (
                  <tr key={name}>
                    <th scope="row">{sentenceCase(name)}</th>
                    <td>
                      <FreshnessBadge state={feed.state} />
                    </td>
                    <td className="figures">
                      {feed.age_seconds != null
                        ? `${formatClock(feed.source_timestamp, true)} (${formatDuration(feed.age_seconds)} ago)`
                        : "never received"}
                    </td>
                    <td className="num">{feed.accepted ?? "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>
          {schedule ? (
            <p className="small secondary" style={{ marginTop: 8 }}>
              Timetable in use: {schedule.routes} routes, {schedule.stops.toLocaleString("en-AU")} stops,{" "}
              {schedule.trips.toLocaleString("en-AU")} trips, valid {schedule.feed_start_date} to{" "}
              {schedule.feed_end_date}.
            </p>
          ) : null}
        </section>
      ) : null}

      <QueryView query={metrics} what="Definitions">
        {(data) => (
          <>
            <section className="stack" aria-label="What each figure means">
              {data.metrics.map((metric) => (
                <article key={metric.name} className="card stack" style={{ gap: 6 }}>
                  <h2 className="card-title">{metric.name}</h2>
                  <p>{metric.definition}</p>
                  <p className="small secondary">
                    <strong>Limits:</strong> {metric.limitations}
                  </p>
                  <p className="small muted">Source: {metric.source}</p>
                </article>
              ))}
            </section>
            <section className="card stack" style={{ gap: 8 }}>
              <h2 className="card-title">Attribution</h2>
              <p>{data.attribution}</p>
              <p className="secondary">{data.disclaimer}</p>
              <p className="small">
                <a href="https://translink.com.au/about-translink/open-data" target="_blank" rel="noreferrer">
                  TransLink open data
                </a>
                {" · "}
                <a href="https://github.com/stevensu04/brispulse" target="_blank" rel="noreferrer">
                  Source code
                </a>
              </p>
            </section>
          </>
        )}
      </QueryView>
    </div>
  );
}
