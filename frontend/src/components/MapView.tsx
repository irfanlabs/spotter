import maplibregl, { type GeoJSONSource, type Map as MlMap } from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import { formatDayTime } from "../lib/format";
import { cumulative, decodePolyline, slicePath, type LngLat } from "../lib/polyline";
import { LEVELS, levelColor, levelMeta } from "../lib/risk";
import type { AnalysisResult, Checkpoint, HeatmapResult } from "../types";

export const ROUTE_COLORS = ["#0B3B8C", "#0E8A8F", "#7A5AF8"];
const STYLE_URL = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";
const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

const DEFAULT_CELL_RADIUS_MI = 18;

/** Heat cell radius in miles, expressed in pixels by zoom (512px tiles, ~38°N). */
function heatRadius(miles: number): maplibregl.ExpressionSpecification {
  const atZoom0 = (miles * 1609.344) / (78271.5 * 0.78);
  return ["interpolate", ["exponential", 2], ["zoom"], 0, atZoom0, 12, atZoom0 * 4096];
}

export interface FocusRequest {
  routeId: string;
  index: number;
  nonce: number;
}

interface Props {
  result: AnalysisResult | null;
  selectedId: string | null;
  focus: FocusRequest | null;
  heatmap: HeatmapResult | null;
  heatHour: number;
  heatVisible: boolean;
  onSelectRoute: (id: string) => void;
  onFocusCheckpoint: (routeId: string, index: number) => void;
}

function popupNode(title: string, rows: [string, string][], badge?: { text: string; color: string }): HTMLElement {
  const root = document.createElement("div");
  root.className = "popup";
  const h = document.createElement("div");
  h.className = "popup-title";
  h.textContent = title;
  root.appendChild(h);
  if (badge) {
    const b = document.createElement("span");
    b.className = "popup-badge";
    b.style.background = badge.color;
    b.textContent = badge.text;
    root.appendChild(b);
  }
  const dl = document.createElement("dl");
  for (const [k, v] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = k;
    const dd = document.createElement("dd");
    dd.textContent = v;
    dl.append(dt, dd);
  }
  root.appendChild(dl);
  return root;
}

function checkpointPopup(c: Checkpoint): HTMLElement {
  const rows: [string, string][] = [
    ["Mile", `${Math.round(c.mile)}`],
    ["ETA", formatDayTime(c.eta)],
    ["Wind", `${c.weather.wind_mph.toFixed(0)} mph`],
    ["Rain", `${c.weather.rain_in_hr.toFixed(2)} in/hr`],
    ["Snow", `${c.weather.snow_in_hr.toFixed(1)} in/hr`],
  ];
  if (c.risk.drivers.length) rows.push(["Why", c.risk.drivers.join("; ")]);
  const m = levelMeta(c.risk.level);
  return popupNode(`Checkpoint ${c.index + 1}`, rows, { text: m.label, color: m.color });
}

export function MapView({ result, selectedId, focus, heatmap, heatHour, heatVisible, onSelectRoute, onFocusCheckpoint }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const [ready, setReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  // Keep callbacks fresh without re-binding map handlers.
  const cbs = useRef({ onSelectRoute, onFocusCheckpoint, result, heatmap, heatHour });
  cbs.current = { onSelectRoute, onFocusCheckpoint, result, heatmap, heatHour };

  // Decode geometries once per result.
  const decoded = useMemo(() => {
    const out = new Map<string, { path: LngLat[]; cum: number[] }>();
    result?.routes.forEach((r) => {
      const path = decodePolyline(r.geometry);
      out.set(r.id, { path, cum: cumulative(path) });
    });
    return out;
  }, [result]);

  // ---- map init
  useEffect(() => {
    if (!container.current) return;
    let map: MlMap;
    try {
      map = new maplibregl.Map({
        container: container.current,
        style: STYLE_URL,
        center: [-96, 38.5],
        zoom: 3.6,
        attributionControl: { compact: true },
        cooperativeGestures: false,
      });
    } catch {
      setMapError("Your browser couldn't start the map (WebGL is required).");
      return;
    }
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-left");

    map.on("error", (e) => {
      const msg = String((e as { error?: Error }).error?.message ?? "");
      if (/style|Failed to fetch|NetworkError/i.test(msg) && !map.isStyleLoaded()) setMapError("The base map couldn't be loaded. Check your connection and refresh.");
    });

    map.on("load", () => {
      map.addSource("heat", { type: "geojson", data: EMPTY });
      map.addSource("routes", { type: "geojson", data: EMPTY });
      map.addSource("segments", { type: "geojson", data: EMPTY });
      map.addSource("checkpoints", { type: "geojson", data: EMPTY });

      map.addLayer({
        id: "heat-layer",
        type: "circle",
        source: "heat",
        paint: {
          "circle-radius": heatRadius(DEFAULT_CELL_RADIUS_MI),
          "circle-blur": 1,
          "circle-color": "rgba(0,0,0,0)",
          "circle-opacity": 0.85,
          "circle-pitch-alignment": "map",
        },
      });
      map.addLayer({
        id: "route-casing",
        type: "line",
        source: "routes",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#fff", "line-width": ["case", ["==", ["get", "selected"], 1], 10, 7], "line-opacity": 0.95 },
      });
      map.addLayer({
        id: "route-line",
        type: "line",
        source: "routes",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": ["get", "color"],
          "line-width": ["case", ["==", ["get", "selected"], 1], 0, 4],
          "line-opacity": 0.75,
        },
      });
      map.addLayer({
        id: "route-risk",
        type: "line",
        source: "segments",
        layout: { "line-cap": "butt", "line-join": "round" },
        paint: { "line-color": ["get", "color"], "line-width": 6 },
      });
      map.addLayer({
        id: "route-hit",
        type: "line",
        source: "routes",
        paint: { "line-color": "#000", "line-width": 18, "line-opacity": 0 },
      });
      map.addLayer({
        id: "cp-layer",
        type: "circle",
        source: "checkpoints",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 3.5, 8, 6, 12, 8],
          "circle-color": ["get", "color"],
          "circle-stroke-color": "#fff",
          "circle-stroke-width": 2,
        },
      });

      map.on("click", "route-hit", (e) => {
        const id = e.features?.[0]?.properties?.id as string | undefined;
        if (id) cbs.current.onSelectRoute(id);
      });
      map.on("click", "cp-layer", (e) => {
        const p = e.features?.[0]?.properties;
        if (p) cbs.current.onFocusCheckpoint(p.routeId as string, Number(p.index));
      });

      const pop = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 14, maxWidth: "260px" });
      popupRef.current = pop;

      map.on("mousemove", (e) => {
        const cp = map.queryRenderedFeatures(e.point, { layers: ["cp-layer"] })[0];
        const hit = !cp && map.queryRenderedFeatures(e.point, { layers: ["route-hit"] })[0];
        map.getCanvas().style.cursor = cp || hit ? "pointer" : "";
        const r = cbs.current.result;
        if (cp && r) {
          const route = r.routes.find((x) => x.id === cp.properties.routeId);
          const c = route?.checkpoints[Number(cp.properties.index)];
          if (c) return void pop.setLngLat([c.lon, c.lat]).setDOMContent(checkpointPopup(c)).addTo(map);
        }
        const heat = map.getLayoutProperty("heat-layer", "visibility") !== "none" ? map.queryRenderedFeatures(e.point, { layers: ["heat-layer"] })[0] : undefined;
        const hm = cbs.current.heatmap;
        if (heat && hm && !hit) {
          const h = cbs.current.heatHour;
          const p = heat.properties as Record<string, number>;
          const level = p[`l${h}`];
          const title = formatDayTime(new Date(new Date(hm.start).getTime() + h * 3600_000).toISOString());
          const content =
            level < 0
              ? popupNode(title, [["Forecast", "Not available"]])
              : popupNode(
                  title,
                  [
                    ["Wind", `${p[`w${h}`]} mph`],
                    ["Rain", `${Number(p[`r${h}`]).toFixed(2)} in/hr`],
                    ["Snow", `${Number(p[`s${h}`]).toFixed(1)} in/hr`],
                  ],
                  { text: levelMeta(level).label, color: levelMeta(level).color },
                );
          return void pop.setLngLat(e.lngLat).setDOMContent(content).addTo(map);
        }
        pop.remove();
      });
      map.on("mouseout", () => pop.remove());

      setReady(true);
    });

    const ro = new ResizeObserver(() => map.resize());
    ro.observe(container.current);
    return () => {
      ro.disconnect();
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, []);

  // ---- route lines, risk segments, checkpoints
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const routesSrc = map.getSource("routes") as GeoJSONSource;
    // Route identity colours follow generation order (A, B, C), matching the cards.
    routesSrc.setData({
      type: "FeatureCollection",
      features: (result?.routes ?? [])
        .slice()
        .sort((a, b) => (a.id === selectedId ? 1 : 0) - (b.id === selectedId ? 1 : 0))
        .map((r) => ({
          type: "Feature" as const,
          properties: { id: r.id, color: ROUTE_COLORS["ABC".indexOf(r.id.slice(-1))], selected: r.id === selectedId ? 1 : 0 },
          geometry: { type: "LineString" as const, coordinates: decoded.get(r.id)!.path },
        })),
    });

    const sel = result?.routes.find((r) => r.id === selectedId);
    const segFeatures: GeoJSON.Feature[] = [];
    const cpFeatures: GeoJSON.Feature[] = [];
    if (sel) {
      const d = decoded.get(sel.id)!;
      const scale = d.cum[d.cum.length - 1] / sel.distance_mi;
      let cursor = 0;
      sel.checkpoints.forEach((c, i) => {
        const next = i === sel.checkpoints.length - 1 ? sel.distance_mi : (c.mile + sel.checkpoints[i + 1].mile) / 2;
        const coords = slicePath(d.path, d.cum, cursor * scale, next * scale);
        if (coords.length > 1) segFeatures.push({ type: "Feature", properties: { color: levelColor(c.risk.level) }, geometry: { type: "LineString", coordinates: coords } });
        cursor = next;
        cpFeatures.push({
          type: "Feature",
          properties: { color: levelColor(c.risk.level), routeId: sel.id, index: c.index },
          geometry: { type: "Point", coordinates: [c.lon, c.lat] },
        });
      });
    }
    (map.getSource("segments") as GeoJSONSource).setData({ type: "FeatureCollection", features: segFeatures });
    (map.getSource("checkpoints") as GeoJSONSource).setData({ type: "FeatureCollection", features: cpFeatures });
  }, [result, selectedId, decoded, ready]);

  // ---- fit + O/D markers on new result
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];
    popupRef.current?.remove();
    if (!result) return;
    const mk = (kind: "origin" | "dest", lon: number, lat: number, label: string) => {
      const el = document.createElement("div");
      el.className = `od-marker ${kind}`;
      el.setAttribute("role", "img");
      el.setAttribute("aria-label", `${kind === "origin" ? "Origin" : "Destination"}: ${label}`);
      el.textContent = kind === "origin" ? "A" : "B";
      markersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([lon, lat]).addTo(map));
    };
    const { origin, destination } = result.request;
    mk("origin", origin.lon, origin.lat, origin.label);
    mk("dest", destination.lon, destination.lat, destination.label);

    const b = new maplibregl.LngLatBounds();
    decoded.forEach((d) => d.path.forEach((p) => b.extend(p)));
    if (!b.isEmpty()) map.fitBounds(b, { padding: { top: 70, bottom: 190, left: 60, right: 60 }, duration: 900, maxZoom: 11 });
  }, [result, decoded, ready]);

  // ---- heatmap data: one flat property per hour, so changing hour needs no new data
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const features: GeoJSON.Feature[] = (heatmap?.cells ?? []).map((c) => {
      const props: Record<string, number> = {};
      c.levels.forEach((l, h) => {
        props[`l${h}`] = l;
        props[`w${h}`] = c.wind[h];
        props[`r${h}`] = c.rain[h];
        props[`s${h}`] = c.snow[h];
      });
      return { type: "Feature", properties: props, geometry: { type: "Point", coordinates: [c.lon, c.lat] } };
    });
    (map.getSource("heat") as GeoJSONSource).setData({ type: "FeatureCollection", features });
    map.setPaintProperty("heat-layer", "circle-radius", heatRadius(heatmap?.cell_radius_mi ?? DEFAULT_CELL_RADIUS_MI));
  }, [heatmap, ready]);

  // ---- heatmap hour + visibility: only the colour expression changes (no requests).
  // Levels without a colour here, including -1 (no forecast), are transparent.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.setLayoutProperty("heat-layer", "visibility", heatVisible && heatmap ? "visible" : "none");
    const stops = LEVELS.flatMap((l) => [l.level, l.level === 0 ? "rgba(47,158,110,0.16)" : hexA(l.color, l.level === 1 ? 0.5 : 0.7)]);
    map.setPaintProperty("heat-layer", "circle-color", ["match", ["get", `l${Math.min(heatHour, heatmap?.hours ?? 48)}`], ...stops, "rgba(0,0,0,0)"]);
  }, [heatHour, heatVisible, heatmap, ready]);

  // ---- focus a checkpoint from the table
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !focus || !result) return;
    const c = result.routes.find((r) => r.id === focus.routeId)?.checkpoints[focus.index];
    if (!c) return;
    map.flyTo({ center: [c.lon, c.lat], zoom: Math.max(map.getZoom(), 8), duration: 700 });
    popupRef.current?.setLngLat([c.lon, c.lat]).setDOMContent(checkpointPopup(c)).addTo(map);
  }, [focus, result, ready]);

  return (
    <div className="map-shell">
      <div ref={container} className="map" aria-label="Route map" />
      {!ready && !mapError && <div className="map-loading"><span className="spinner" /> Loading map…</div>}
      {mapError && (
        <div className="map-error" role="alert">
          <strong>Map unavailable</strong>
          <p>{mapError}</p>
        </div>
      )}
    </div>
  );
}

function hexA(hex: string, a: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}
