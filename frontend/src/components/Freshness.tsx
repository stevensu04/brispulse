import { CircleAlert, CircleCheck, CircleX, Clock } from "lucide-react";
import type { FeedMeta, Freshness, Meta } from "../api/client";
import { formatClock, formatDuration } from "../lib/format";

const WORDS: Record<Freshness, string> = {
  live: "Live",
  delayed: "Delayed",
  stale: "Stale",
  unavailable: "Unavailable",
};

const ICONS = { live: CircleCheck, delayed: Clock, stale: CircleAlert, unavailable: CircleX };

const ORDER: Freshness[] = ["live", "delayed", "stale", "unavailable"];

/** The least fresh state among the feeds a response was built from. */
export function worstState(feeds: Meta["feeds"]): Freshness | null {
  const states = Object.values(feeds).map((feed) => (feed as FeedMeta).state);
  if (states.length === 0) return null;
  return states.reduce((worst, state) => (ORDER.indexOf(state) > ORDER.indexOf(worst) ? state : worst));
}

/** Freshness as an icon and a word. The colour repeats what the word already says. */
export function FreshnessBadge({ state }: { state: Freshness }) {
  const Icon = ICONS[state];
  return (
    <span className="chip freshness" data-state={state}>
      <Icon size={14} aria-hidden="true" />
      {WORDS[state]}
    </span>
  );
}

// Which feed's age to quote when a response draws on several. Vehicle positions come
// first: they are what "now" means on most screens, and alerts are fetched less often,
// so quoting the oldest feed would make live vehicle data look minutes old.
const PRIMARY: (keyof Meta["feeds"])[] = ["vehicle_positions", "trip_updates", "alerts"];

/** "Live · Vehicle data from TransLink 14 s ago (09:03:20 Brisbane time)". */
export function FreshnessLine({ meta }: { meta: Meta }) {
  const state = worstState(meta.feeds);
  if (state === null) return null;
  const name = PRIMARY.find((feed) => meta.feeds[feed] !== undefined);
  const feed = name ? (meta.feeds[name] as FeedMeta) : undefined;
  const what = name === "alerts" ? "Alerts" : name === "trip_updates" ? "Trip data" : "Vehicle data";
  return (
    <p className="row small secondary" aria-live="polite">
      <FreshnessBadge state={state} />
      {feed?.age_seconds != null ? (
        <span>
          {what} from TransLink {formatDuration(feed.age_seconds)} ago (
          {formatClock(feed.source_timestamp, true)} Brisbane time)
        </span>
      ) : (
        <span>No data received yet</span>
      )}
    </p>
  );
}
