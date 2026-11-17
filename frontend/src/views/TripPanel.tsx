import { X } from "lucide-react";
import { useTrip } from "../api/hooks";
import { DelayText } from "../components/Delay";
import { Notes, QueryView } from "../components/States";
import { formatClock } from "../lib/format";
import { href } from "../lib/router";
import { useBandLimits } from "../lib/useBandLimits";
import { TableScroll } from "../components/TableScroll";

/** One trip: where it is headed and TransLink's prediction for each stop still ahead. */
export function TripPanel({
  tripId,
  onClose,
  showTitle = true,
}: {
  tripId: string;
  onClose?: () => void;
  /** False when the surrounding panel already names the trip. */
  showTitle?: boolean;
}) {
  const query = useTrip(tripId);
  const limits = useBandLimits();
  return (
    <section aria-label="Trip details" className="stack" style={{ gap: 12 }}>
      <QueryView query={query} what="Trip">
        {(trip, notes) => {
          const realtime = trip.realtime;
          return (
            <>
              {showTitle ? (
              <div className="row spread" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
                <div>
                  <h2 className="card-title">
                    {trip.route?.short_name ? `${trip.route.short_name} · ` : ""}
                    {trip.headsign ?? "Trip"}
                  </h2>
                  {trip.route ? (
                    <a className="small" href={href("routes", trip.route.route_id)}>
                      {trip.route.long_name ?? "Route details"}
                    </a>
                  ) : null}
                </div>
                {onClose ? (
                  <button type="button" className="icon-button" onClick={onClose} aria-label="Close trip details">
                    <X size={18} aria-hidden="true" />
                  </button>
                ) : null}
              </div>
              ) : null}
              <Notes notes={notes} />
              {realtime === null ? (
                <p className="secondary">No live information for this trip right now.</p>
              ) : (
                <>
                  <dl className="definition-list">
                    <dt>Status</dt>
                    <dd>
                      {realtime.relationship === "canceled"
                        ? "Cancelled"
                        : realtime.running === null
                          ? "Unknown: vehicle positions are unavailable"
                          : realtime.running
                            ? "Running"
                            : "Not running now"}
                    </dd>
                    <dt>Predicted delay</dt>
                    <dd>
                      <DelayText seconds={realtime.predicted_delay_s} limits={limits} />
                      {realtime.delay_implausible ? (
                        <span className="small muted"> (over an hour: probably a data fault)</span>
                      ) : null}
                    </dd>
                    <dt>Scheduled start</dt>
                    <dd className="figures">{formatClock(realtime.scheduled_start)}</dd>
                  </dl>
                  {realtime.stops.length > 0 ? (
                    <TableScroll label="Predicted times at the next stops">
                      <table>
                        <thead>
                          <tr>
                            <th scope="col">Next stops</th>
                            <th scope="col" className="num">Predicted</th>
                            <th scope="col" className="num">Delay</th>
                          </tr>
                        </thead>
                        <tbody>
                          {realtime.stops.slice(0, 12).map((stop, index) => (
                            <tr key={`${stop.stop.stop_id}-${stop.stop_sequence ?? index}`}>
                              <td>{stop.stop.name ?? `Stop ${stop.stop.stop_id}`}</td>
                              <td className="num">{formatClock(stop.arrival_time ?? stop.departure_time)}</td>
                              <td className="num">
                                <DelayText seconds={stop.arrival_delay_s ?? stop.departure_delay_s} limits={limits} />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {realtime.stops.length > 12 ? (
                        <p className="small muted">and {realtime.stops.length - 12} more stops</p>
                      ) : null}
                    </TableScroll>
                  ) : null}
                </>
              )}
            </>
          );
        }}
      </QueryView>
    </section>
  );
}
