import { useMetrics } from "../api/hooks";
import { type BandLimits, DEFAULT_BANDS } from "./format";

/** The early/late limits the API uses, so the app classifies delays the same way. */
export function useBandLimits(): BandLimits {
  const thresholds = useMetrics().data?.data?.thresholds;
  if (!thresholds) return DEFAULT_BANDS;
  return {
    earlySeconds: thresholds["delay_early_s"] ?? DEFAULT_BANDS.earlySeconds,
    lateSeconds: thresholds["delay_late_s"] ?? DEFAULT_BANDS.lateSeconds,
  };
}
