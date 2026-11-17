import type { DelaySummary } from "../api/client";
import { type BandLimits, delayBand, formatCount, formatDelay, formatDuration, percent } from "../lib/format";

/** A predicted delay in words, coloured by band. "no prediction" when there is none. */
export function DelayText({ seconds, limits }: { seconds: number | null | undefined; limits: BandLimits }) {
  if (seconds === null || seconds === undefined) return <span className="muted">no prediction</span>;
  return (
    <span className="delay-text" data-band={delayBand(seconds, limits)}>
      {formatDelay(seconds)}
    </span>
  );
}

const BANDS = [
  { key: "early", word: "Early" },
  { key: "within", word: "Within band" },
  { key: "late", word: "Late" },
] as const;

/**
 * How running trips split between early, within band and late.
 *
 * One stacked bar, because the three counts are parts of one whole. Every segment is
 * also named and counted in text below it, so nothing depends on telling colours apart.
 */
export function DelayBands({ summary, limits }: { summary: DelaySummary; limits: BandLimits }) {
  const counts = { early: summary.early, within: summary.within_band, late: summary.late };
  const total = summary.sample_size;
  const ranges = {
    early: `more than ${formatDuration(limits.earlySeconds)} early`,
    within: `${formatDuration(limits.earlySeconds)} early to ${formatDuration(limits.lateSeconds)} late`,
    late: `more than ${formatDuration(limits.lateSeconds)} late`,
  };
  if (total === 0) {
    return <p className="secondary small">No running trips with a predicted delay right now.</p>;
  }
  return (
    <div>
      <div
        className="bands-bar"
        role="img"
        aria-label={`Of ${total} running trips: ${counts.early} early, ${counts.within} within band, ${counts.late} late.`}
      >
        {BANDS.filter(({ key }) => counts[key] > 0).map(({ key, word }) => (
          <div
            key={key}
            className="bands-segment"
            data-band={key}
            style={{ flexGrow: counts[key], flexBasis: 0 }}
            title={`${word}: ${formatCount(counts[key])} trips (${percent(counts[key], total)})`}
          />
        ))}
      </div>
      <ul className="bands-legend">
        {BANDS.map(({ key, word }) => (
          <li key={key}>
            <span className="swatch" data-band={key} aria-hidden="true" />
            <span>
              <span className="band-word">{word}</span>{" "}
              <span className="figures">
                {formatCount(counts[key])} ({percent(counts[key], total)})
              </span>
              <br />
              <span className="small muted">{ranges[key]}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
