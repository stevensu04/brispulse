import type { FeatureCollection } from "geojson";
import { X } from "lucide-react";
import { type GeoJSONSource, Map as MapLibreMap, NavigationControl, setWorkerUrl } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
// The map's worker must be a file the bundler knows about; its default guess at the
// worker's address does not survive bundling.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Vehicle } from "../api/client";
import { useVehicles } from "../api/hooks";
import { DelayText } from "../components/Delay";
import { FreshnessBadge, worstState } from "../components/Freshness";
import { ModeFilter, ModeLabel } from "../components/Mode";
import { ErrorState, StartingUp, Unavailable } from "../components/States";
import { type BandLimits, delayBand, formatClock, formatCount, sentenceCase } from "../lib/format";
import { href } from "../lib/router";
import type { Theme } from "../lib/theme";
import { useBandLimits } from "../lib/useBandLimits";
import { TripPanel } from "./TripPanel";

setWorkerUrl(workerUrl);

// OpenFreeMap: free OpenStreetMap-based tiles, no key or registration. Attribution is
// added by the map itself.
const STYLES: Record<Theme, string> = {
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
};
const BRISBANE: [number, number] = [153.026, -27.469];
const SOURCE = "vehicles";
// Half the side of the square searched around a tap, in CSS pixels (a 44 px target).
const HIT_RADIUS = 22;

type Band = "early" | "within" | "late" | "none";

function bandOf(vehicle: Vehicle, limits: BandLimits): Band {
  return vehicle.predicted_delay_s == null ? "none" : delayBand(vehicle.predicted_delay_s, limits);
}

function toGeoJson(vehicles: Vehicle[], limits: BandLimits): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: vehicles.map((vehicle) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [vehicle.lon, vehicle.lat] },
      properties: { id: vehicle.vehicle_id, band: bandOf(vehicle, limits), fresh: vehicle.fresh },
    })),
  };
}

/** Read a design token, so the map's colours are the same ones the rest of the app uses. */
function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function addVehicleLayers(map: MapLibreMap, data: FeatureCollection, selected: string | null) {
  if (map.getSource(SOURCE)) return;
  map.addSource(SOURCE, { type: "geojson", data });
  map.addLayer({
    id: "vehicles",
    type: "circle",
    source: SOURCE,
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 2.5, 11, 4.5, 14, 7],
      "circle-color": [
        "match",
        ["get", "band"],
        "early",
        token("--delay-early"),
        "late",
        token("--delay-late"),
        "within",
        token("--text-secondary"),
        token("--surface"),
      ],
      // "Last seen" positions (not fresh) are drawn faint.
      "circle-opacity": ["case", ["get", "fresh"], 1, 0.35],
      "circle-stroke-width": ["case", ["==", ["get", "band"], "none"], 1.5, 1],
      "circle-stroke-color": ["case", ["==", ["get", "band"], "none"], token("--text-muted"), token("--surface")],
      "circle-stroke-opacity": ["case", ["get", "fresh"], 1, 0.4],
    },
  });
  map.addLayer({
    id: "vehicle-selected",
    type: "circle",
    source: SOURCE,
    filter: ["==", ["get", "id"], selected ?? ""],
    paint: {
      "circle-radius": 12,
      "circle-color": "transparent",
      "circle-stroke-width": 3,
      "circle-stroke-color": token("--accent"),
    },
  });
}

function VehicleDetail({ vehicle, limits, onClose }: { vehicle: Vehicle; limits: BandLimits; onClose: () => void }) {
  return (
    <aside className="map-panel map-detail stack" style={{ gap: 12 }} aria-label="Selected vehicle">
      <div className="row spread" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
        <div>
          <h2 className="card-title">
            {vehicle.route_short_name ? `${vehicle.route_short_name} · ` : ""}
            {vehicle.headsign ?? "Vehicle"}
          </h2>
          <p className="small secondary">
            <ModeLabel mode={vehicle.mode} />
          </p>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close vehicle details">
          <X size={18} aria-hidden="true" />
        </button>
      </div>
      <dl className="definition-list">
        <dt>Predicted delay</dt>
        <dd>
          <DelayText seconds={vehicle.predicted_delay_s} limits={limits} />
        </dd>
        <dt>{vehicle.status === "stopped_at" ? "Stopped at" : "Heading to"}</dt>
        <dd>{vehicle.stop?.name ?? (vehicle.stop ? `Stop ${vehicle.stop.stop_id}` : "Not given")}</dd>
        <dt>Position reported</dt>
        <dd className="figures">
          {formatClock(vehicle.reported_at, true)}
          {vehicle.fresh ? "" : " (last seen: over 90 s ago)"}
        </dd>
        <dt>Vehicle</dt>
        <dd>{vehicle.label ?? vehicle.vehicle_id.slice(0, 12)}</dd>
      </dl>
      {!vehicle.matched ? (
        <p className="small secondary">
          This vehicle&rsquo;s trip is not in the current timetable, so it is not counted in any figure.
        </p>
      ) : null}
      {vehicle.route_id ? (
        <a className="button" href={href("routes", vehicle.route_id)}>
          Route {vehicle.route_short_name ?? ""} details
        </a>
      ) : null}
      {vehicle.trip_id && vehicle.matched ? <TripPanel tripId={vehicle.trip_id} showTitle={false} /> : null}
    </aside>
  );
}

export function MapView({ theme }: { theme: Theme }) {
  const query = useVehicles();
  const limits = useBandLimits();
  const [mode, setMode] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);

  const all = query.data?.data ?? null;
  const vehicles = useMemo(
    () => (all ?? []).filter((vehicle) => mode === null || vehicle.mode === mode),
    [all, mode],
  );
  const geojson = useMemo(() => toGeoJson(vehicles, limits), [vehicles, limits]);
  const selected = useMemo(
    () => (all ?? []).find((vehicle) => vehicle.vehicle_id === selectedId) ?? null,
    [all, selectedId],
  );

  // The latest values, for map callbacks that outlive a render.
  const latest = useRef({ geojson, selectedId });
  useEffect(() => {
    latest.current = { geojson, selectedId };
  }, [geojson, selectedId]);

  useEffect(() => {
    if (!container.current) return;
    const map = new MapLibreMap({
      container: container.current,
      style: STYLES[theme],
      center: BRISBANE,
      zoom: 10,
      minZoom: 7,
      maxBounds: [
        [151.0, -29.2],
        [154.6, -25.4],
      ],
    });
    mapRef.current = map;
    map.addControl(new NavigationControl({ showCompass: false }), "bottom-right");
    // Tile and style failures are otherwise silent; surface them in the console.
    map.on("error", (event) => console.error("map:", event.error?.message ?? event));
    // A style (re)load drops custom layers, so they are added whenever one finishes.
    map.on("style.load", () => addVehicleLayers(map, latest.current.geojson, latest.current.selectedId));
    // The dots are small, so a tap selects the nearest vehicle within a finger's width
    // rather than requiring a hit on the dot itself.
    map.on("click", (event) => {
      if (!map.getLayer("vehicles")) return;
      const { x, y } = event.point;
      const nearby = map.queryRenderedFeatures(
        [
          [x - HIT_RADIUS, y - HIT_RADIUS],
          [x + HIT_RADIUS, y + HIT_RADIUS],
        ],
        { layers: ["vehicles"] },
      );
      let best: string | null = null;
      let bestDistance = Infinity;
      for (const feature of nearby) {
        if (feature.geometry.type !== "Point") continue;
        const [lon, lat] = feature.geometry.coordinates as [number, number];
        const at = map.project([lon, lat]);
        const distance = Math.hypot(at.x - x, at.y - y);
        const id = feature.properties?.["id"];
        if (typeof id === "string" && distance < bestDistance) {
          best = id;
          bestDistance = distance;
        }
      }
      if (best !== null) setSelectedId(best);
    });
    map.on("mouseenter", "vehicles", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "vehicles", () => (map.getCanvas().style.cursor = ""));
    return () => {
      mapRef.current = null;
      map.remove();
    };
    // The map is created once; theme changes are handled below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const firstTheme = useRef(theme);
  useEffect(() => {
    if (theme === firstTheme.current) return;
    firstTheme.current = theme;
    mapRef.current?.setStyle(STYLES[theme]);
  }, [theme]);

  useEffect(() => {
    const source = mapRef.current?.getSource(SOURCE) as GeoJSONSource | undefined;
    source?.setData(geojson);
  }, [geojson]);

  useEffect(() => {
    const map = mapRef.current;
    if (map?.getLayer("vehicle-selected")) {
      map.setFilter("vehicle-selected", ["==", ["get", "id"], selectedId ?? ""]);
    }
  }, [selectedId]);

  const meta = query.data?.meta;
  const problem = query.error ?? query.failureReason;
  const state = meta ? worstState({ vehicle_positions: meta.feeds.vehicle_positions! }) : null;
  const shownFresh = vehicles.filter((vehicle) => vehicle.fresh).length;

  return (
    <div className="map-layout">
      <div ref={container} className="map-canvas" role="region" aria-label="Map of vehicle positions" />
      <div className="map-controls">
        <div className="map-panel" style={{ padding: 6 }}>
          <ModeFilter value={mode} onChange={setMode} />
        </div>
        {state && all ? (
          <div className="map-panel row small" style={{ padding: "6px 12px" }} aria-live="polite">
            <FreshnessBadge state={state} />
            <span className="figures">{formatCount(shownFresh)} vehicles</span>
          </div>
        ) : null}
      </div>
      <div className="map-panel map-legend" aria-label="Legend">
        <strong>Predicted delay</strong>
        <ul>
          <li>
            <span className="dot" data-band="early" /> Early (over {Math.round(limits.earlySeconds / 60)} min)
          </li>
          <li>
            <span className="dot" data-band="within" /> Within band
          </li>
          <li>
            <span className="dot" data-band="late" /> Late (over {Math.round(limits.lateSeconds / 60)} min)
          </li>
          <li>
            <span className="dot" data-band="none" /> No prediction
          </li>
        </ul>
      </div>
      {query.data === undefined && problem ? (
        <div className="map-overlay">
          {problem.isStarting ? (
            <StartingUp />
          ) : (
            <ErrorState error={problem} onRetry={() => void query.refetch()} />
          )}
        </div>
      ) : null}
      {query.data && all === null ? (
        <div className="map-overlay">
          <Unavailable what="Vehicle positions" notes={query.data.meta.notes} />
        </div>
      ) : null}
      {selectedId && selected ? (
        <VehicleDetail vehicle={selected} limits={limits} onClose={() => setSelectedId(null)} />
      ) : null}
      {selectedId && !selected && all ? (
        <aside className="map-panel map-detail stack" aria-label="Selected vehicle">
          <p>This vehicle is no longer reporting a position.</p>
          <button type="button" className="button" onClick={() => setSelectedId(null)}>
            Close
          </button>
        </aside>
      ) : null}
      <p className="sr-only">
        The map shows {formatCount(shownFresh)} vehicles. The same information is available as text
        under Routes. {state ? `Vehicle data is ${sentenceCase(state)}.` : ""}
      </p>
    </div>
  );
}
