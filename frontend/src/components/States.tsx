import { CircleAlert, Info, LoaderCircle, MoonStar, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import type { ApiError } from "../api/client";
import type { Query } from "../api/hooks";

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="stack" role="status" aria-label={label}>
      <div className="skeleton" style={{ height: 96 }} />
      <div className="skeleton" style={{ height: 180 }} />
    </div>
  );
}

/** The server sleeps when nobody is using it; this is the first thing a visitor sees then. */
export function StartingUp() {
  return (
    <div className="state-block" role="status">
      <MoonStar size={32} aria-hidden="true" />
      <h2>Waking up</h2>
      <p>
        BrisPulse runs on a server that sleeps when nobody is using it. It is starting now and
        loading TransLink&rsquo;s timetable. Live data usually appears within a minute.
      </p>
      <LoaderCircle size={20} className="spin" aria-hidden="true" />
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry: () => void }) {
  return (
    <div className="state-block" role="alert">
      <CircleAlert size={32} aria-hidden="true" />
      <h2>{error.status === 404 ? "Not found" : "Something went wrong"}</h2>
      <p>{error.message}</p>
      <button type="button" className="button" onClick={onRetry}>
        <RefreshCw size={16} aria-hidden="true" />
        Try again
      </button>
    </div>
  );
}

/** Data the API withheld. Says why, in the API's own words, instead of showing zeros. */
export function Unavailable({ what, notes }: { what: string; notes: string[] }) {
  return (
    <div className="state-block" role="status">
      <CircleAlert size={28} aria-hidden="true" />
      <h2>{what} unavailable</h2>
      <p>
        BrisPulse has no recent data for this from TransLink, so nothing is shown rather than
        something out of date.
      </p>
      <Notes notes={notes} />
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="state-block">
      <p>{children}</p>
    </div>
  );
}

/** Caveats the API attached to a response. */
export function Notes({ notes, tone = "warning" }: { notes: string[]; tone?: "warning" | "info" }) {
  if (notes.length === 0) return null;
  const Icon = tone === "info" ? Info : CircleAlert;
  return (
    <div className="notice" data-tone={tone}>
      <Icon size={18} aria-hidden="true" />
      {notes.length === 1 ? (
        <span>{notes[0]}</span>
      ) : (
        <ul>
          {notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Renders a query's loading, starting, error and unavailable states, and calls
 * `children` only when there is data to show.
 */
export function QueryView<T>({
  query,
  what,
  children,
}: {
  query: Query<T>;
  what: string;
  children: (data: T, notes: string[]) => ReactNode;
}) {
  if (query.data === undefined) {
    // While a request is being retried the query has no final error yet, only the
    // reason for its latest failure. That is when the server is most likely waking.
    const problem = query.error ?? query.failureReason;
    if (problem) {
      if (problem.isStarting) return <StartingUp />;
      return <ErrorState error={problem} onRetry={() => void query.refetch()} />;
    }
    return <Loading label={`Loading ${what.toLowerCase()}`} />;
  }
  const { data, meta } = query.data;
  if (data === null) return <Unavailable what={what} notes={meta.notes} />;
  return <>{children(data, meta.notes)}</>;
}
