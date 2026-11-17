/**
 * The one place that talks to the BrisPulse API.
 *
 * Types come from `schema.d.ts`, which is generated from the backend's OpenAPI
 * document (`npm run api:types`), so a change to the API shows up here as a type error.
 */
import type { components } from "./schema";

type Schemas = components["schemas"];

export type Freshness = Schemas["Freshness"];
export type FeedMeta = Schemas["FeedMeta"];
export type Meta = Schemas["Meta"];
export type StatusData = Schemas["StatusData"];
export type OverviewData = Schemas["OverviewData"];
export type DelaySummary = Schemas["DelaySummaryOut"];
export type Vehicle = Schemas["VehicleOut"];
export type RouteSummary = Schemas["RouteSummary"];
export type RouteDetail = Schemas["RouteDetail"];
export type TripBrief = Schemas["TripBrief"];
export type TripDetail = Schemas["TripDetail"];
export type Alert = Schemas["AlertOut"];
export type MetricsData = Schemas["MetricsData"];
export type AnalyticsNow = Schemas["AnalyticsNow"];
export type RouteLateness = Schemas["RouteLateness"];

/** Every response has this shape. `data` is null when it cannot be given. */
export interface Envelope<T> {
  data: T | null;
  meta: Meta;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** The server is waking up or still loading its schedule: worth waiting for. */
  get isStarting(): boolean {
    return this.status === 0 || this.status === 502 || this.status === 503 || this.status === 504;
  }
}

export async function getEnvelope<T>(path: string, signal?: AbortSignal): Promise<Envelope<T>> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, { headers: { Accept: "application/json" }, signal });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, "network", "The server could not be reached.");
  }
  if (!response.ok) {
    let code = "http_error";
    let message = `The server answered ${response.status}.`;
    try {
      const body = (await response.json()) as { error?: { code?: string; message?: string } };
      code = body.error?.code ?? code;
      message = body.error?.message ?? message;
    } catch {
      // A proxy's HTML error page: keep the generic message.
    }
    throw new ApiError(response.status, code, message);
  }
  return (await response.json()) as Envelope<T>;
}
