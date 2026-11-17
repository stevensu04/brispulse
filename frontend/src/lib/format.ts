/** Wording and classification shared by every view. */

export const TIME_ZONE = "Australia/Brisbane";

export type DelayBand = "early" | "within" | "late";

/** The band limits, as published by the API under /meta/metrics. */
export interface BandLimits {
  earlySeconds: number;
  lateSeconds: number;
}

// Used only until the API's own values have loaded; they match its defaults.
export const DEFAULT_BANDS: BandLimits = { earlySeconds: 60, lateSeconds: 300 };

export function delayBand(delaySeconds: number, limits: BandLimits = DEFAULT_BANDS): DelayBand {
  if (delaySeconds < -limits.earlySeconds) return "early";
  if (delaySeconds > limits.lateSeconds) return "late";
  return "within";
}

/** "4 min late", "2 min early", "on time". Always says which way, never just a sign. */
export function formatDelay(delaySeconds: number | null | undefined): string {
  if (delaySeconds === null || delaySeconds === undefined) return "no prediction";
  const minutes = Math.round(Math.abs(delaySeconds) / 60);
  if (minutes === 0) return "on time";
  return `${minutes} min ${delaySeconds > 0 ? "late" : "early"}`;
}

/** Seconds as a compact duration: "45 s", "3 min", "2 h 5 min". */
export function formatDuration(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds));
  // Whole minutes read better as minutes ("1 min", not "60 s").
  if (whole < 90 && (whole < 60 || whole % 60 !== 0)) return `${whole} s`;
  const minutes = Math.round(whole / 60);
  if (minutes < 90) return `${minutes} min`;
  const rest = minutes % 60;
  return rest === 0 ? `${Math.floor(minutes / 60)} h` : `${Math.floor(minutes / 60)} h ${rest} min`;
}

const clock = new Intl.DateTimeFormat("en-AU", {
  timeZone: TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const clockSeconds = new Intl.DateTimeFormat("en-AU", {
  timeZone: TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});
const dayAndClock = new Intl.DateTimeFormat("en-AU", {
  timeZone: TIME_ZONE,
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** Brisbane wall-clock time, whatever the viewer's own time zone is. */
export function formatClock(iso: string | null | undefined, withSeconds = false): string {
  if (!iso) return "–";
  return (withSeconds ? clockSeconds : clock).format(new Date(iso));
}

export function formatDayAndClock(iso: string | null | undefined): string {
  if (!iso) return "–";
  return dayAndClock.format(new Date(iso));
}

export function formatCount(value: number): string {
  return value.toLocaleString("en-AU");
}

export function percent(part: number, whole: number): string {
  if (whole <= 0) return "–";
  return `${Math.round((part / whole) * 100)}%`;
}

const MODE_LABELS: Record<string, string> = {
  bus: "Bus",
  rail: "Train",
  ferry: "Ferry",
  tram: "Tram",
  unknown: "Unknown",
};

export const MODE_ORDER = ["bus", "rail", "ferry", "tram"] as const;

export function modeLabel(mode: string | null | undefined): string {
  return MODE_LABELS[mode ?? "unknown"] ?? (mode ?? "Unknown");
}

/** "construction" -> "Construction", "stop_moved" -> "Stop moved". */
export function sentenceCase(code: string): string {
  const words = code.replace(/_/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}
