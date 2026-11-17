import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";
import {
  ApiError,
  getEnvelope,
  type Alert,
  type Envelope,
  type MetricsData,
  type OverviewData,
  type RouteDetail,
  type RouteSummary,
  type StatusData,
  type TripDetail,
  type Vehicle,
} from "./client";

// TransLink refreshes its feeds every 10-30 s and the API caches for 10 s, so asking
// more often than this would only repeat the same answer.
const LIVE_MS = 15_000;
const SLOW_MS = 60_000;

export type Query<T> = UseQueryResult<Envelope<T>, ApiError>;

function useEnvelope<T>(path: string, refetchMs: number, enabled = true): Query<T> {
  return useQuery<Envelope<T>, ApiError>({
    queryKey: [path],
    queryFn: ({ signal }) => getEnvelope<T>(path, signal),
    refetchInterval: refetchMs,
    // Keep showing the last answer while the next one loads, instead of flashing empty.
    placeholderData: keepPreviousData,
    enabled,
    // While the server is waking, keep trying quickly; give up fast on real errors.
    retry: (failures, error) => error.isStarting && failures < 30,
    retryDelay: 2_000,
  });
}

export const useStatus = () => useEnvelope<StatusData>("/status", LIVE_MS);
export const useOverview = () => useEnvelope<OverviewData>("/overview", LIVE_MS);
export const useVehicles = () => useEnvelope<Vehicle[]>("/vehicles", LIVE_MS);
export const useRoutes = () => useEnvelope<RouteSummary[]>("/routes", LIVE_MS * 2);
export const useRoute = (routeId: string) =>
  useEnvelope<RouteDetail>(`/routes/${encodeURIComponent(routeId)}`, LIVE_MS);
export const useTrip = (tripId: string | null) =>
  useEnvelope<TripDetail>(`/trips/${encodeURIComponent(tripId ?? "")}`, LIVE_MS, tripId !== null);
export const useAlerts = () => useEnvelope<Alert[]>("/alerts", SLOW_MS);
export const useMetrics = () => useEnvelope<MetricsData>("/meta/metrics", SLOW_MS * 10);
