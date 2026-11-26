import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, analyze, fetchHeatmap } from "./api";
import { CheckpointTable } from "./components/CheckpointTable";
import { HeatmapControl } from "./components/HeatmapControl";
import { IconAlert, IconClose, IconCloud, IconRefresh } from "./components/Icons";
import { MapView, ROUTE_COLORS, type FocusRequest } from "./components/MapView";
import { Recommendation } from "./components/Recommendation";
import { RiskLegend } from "./components/RiskBits";
import { RouteCard } from "./components/RouteCard";
import { TripForm } from "./components/TripForm";
import type { FieldErrors } from "./lib/validation";
import type { AnalysisResult, AnalyzeRequest, HeatmapResult } from "./types";

type Status = "idle" | "loading" | "ready" | "error";

const FIELD_MAP: Record<string, keyof FieldErrors> = {
  origin: "origin",
  destination: "destination",
  departure: "departure",
  load_weight_lb: "load",
};

function serverFieldErrors(err: ApiError | null): FieldErrors {
  const out: FieldErrors = {};
  if (!err || err.code !== "VALIDATION_ERROR") return out;
  for (const [k, v] of Object.entries(err.fields)) {
    const key = FIELD_MAP[k];
    if (key) out[key] = Array.isArray(v) ? String(v[0]) : typeof v === "string" ? v : "Invalid value.";
  }
  return out;
}

export default function App() {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<"routes" | "checkpoints">("routes");
  const [focus, setFocus] = useState<FocusRequest | null>(null);

  const [heatStatus, setHeatStatus] = useState<Status>("idle");
  const [heat, setHeat] = useState<HeatmapResult | null>(null);
  const [hour, setHour] = useState(0);
  const [heatVisible, setHeatVisible] = useState(true);

  const lastReq = useRef<AnalyzeRequest | null>(null);
  const analyzeCtrl = useRef<AbortController | null>(null);
  const heatCtrl = useRef<AbortController | null>(null);
  const focusNonce = useRef(0);

  const loadHeat = useCallback(async (res: AnalysisResult, req: AnalyzeRequest) => {
    heatCtrl.current?.abort();
    const ctrl = (heatCtrl.current = new AbortController());
    setHeatStatus("loading");
    try {
      const data = await fetchHeatmap(res.routes.map((r) => r.geometry), req.departure, req.load_weight_lb, ctrl.signal);
      if (ctrl.signal.aborted) return;
      setHeat(data);
      setHeatStatus("ready");
    } catch {
      if (!ctrl.signal.aborted) setHeatStatus("error");
    }
  }, []);

  const run = useCallback(
    async (req: AnalyzeRequest) => {
      lastReq.current = req;
      analyzeCtrl.current?.abort();
      heatCtrl.current?.abort();
      const ctrl = (analyzeCtrl.current = new AbortController());
      setStatus("loading");
      setError(null);
      // Never leave a previous trip's routes on screen while a new one is analyzed.
      setResult(null);
      setSelectedId(null);
      setFocus(null);
      setHeat(null);
      setHeatStatus("idle");
      try {
        const res = await analyze(req, ctrl.signal);
        if (ctrl.signal.aborted) return;
        setResult(res);
        setSelectedId(res.recommendation.route_id);
        setHour(0);
        setTab("routes");
        setStatus("ready");
        void loadHeat(res, req);
      } catch (e) {
        if (ctrl.signal.aborted) return;
        setStatus("error");
        setError(e instanceof ApiError ? e : new ApiError("Something unexpected happened. Please try again.", "UNKNOWN", 0, {}, true));
      }
    },
    [loadHeat],
  );

  useEffect(() => () => {
    analyzeCtrl.current?.abort();
    heatCtrl.current?.abort();
  }, []);

  const selected = useMemo(() => result?.routes.find((r) => r.id === selectedId) ?? null, [result, selectedId]);
  const fieldErrors = serverFieldErrors(error);
  // Errors that map to a form field render beside it; everything else gets the banner.
  const bannerError = error && Object.keys(fieldErrors).length === 0 ? error : null;
  const busy = status === "loading";

  const focusCheckpoint = useCallback((routeId: string, index: number) => {
    setFocus({ routeId, index, nonce: ++focusNonce.current });
    setSelectedId(routeId);
    setTab("checkpoints");
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden><IconCloud width={20} height={20} /></span>
          <div>
            <h1>Spotter</h1>
            <p>Weather-aware truck routing</p>
          </div>
        </div>
        <RiskLegend compact />
      </header>

      <main className="layout">
        <aside className="sidebar" aria-label="Trip planner">
          <TripForm busy={busy} serverFieldErrors={fieldErrors} onSubmit={run} />

          {bannerError && (
            <div className="alert" role="alert">
              <IconAlert />
              <div>
                <strong>{titleFor(bannerError)}</strong>
                <p>{bannerMessage(bannerError)}</p>
                {bannerError.retryable && lastReq.current && (
                  <button className="link" onClick={() => run(lastReq.current!)}>
                    <IconRefresh width={14} height={14} /> Try again
                  </button>
                )}
              </div>
              <button className="icon-btn ghost" onClick={() => setError(null)} aria-label="Dismiss"><IconClose width={16} height={16} /></button>
            </div>
          )}

          {busy && <LoadingSkeleton />}

          {!busy && result && selected && (
            <section className="results" aria-live="polite">
              <Recommendation result={result} />
              <div className="tabs" role="tablist">
                <button role="tab" aria-selected={tab === "routes"} className={tab === "routes" ? "on" : ""} onClick={() => setTab("routes")}>
                  Routes <span>{result.routes.length}</span>
                </button>
                <button role="tab" aria-selected={tab === "checkpoints"} className={tab === "checkpoints" ? "on" : ""} onClick={() => setTab("checkpoints")}>
                  Checkpoints <span>{selected.checkpoints.length}</span>
                </button>
              </div>

              {tab === "routes" ? (
                <div className="route-list">
                  {result.routes.length < 3 && <p className="note">Only {result.routes.length} distinct drivable route{result.routes.length === 1 ? "" : "s"} exist{result.routes.length === 1 ? "s" : ""} between these locations.</p>}
                  {result.routes.map((r) => (
                    <RouteCard key={r.id} route={r} selected={r.id === selectedId} color={ROUTE_COLORS["ABC".indexOf(r.id.slice(-1))]} onSelect={() => setSelectedId(r.id)} />
                  ))}
                </div>
              ) : (
                <>
                  <p className="note">
                    {selected.name} · sampled every {selected.interval_miles} mi using the truck's estimated arrival time at each point.
                  </p>
                  <CheckpointTable route={selected} activeIndex={focus?.routeId === selected.id ? focus.index : null} onFocus={(i) => focusCheckpoint(selected.id, i)} />
                </>
              )}
              <p className="attribution">Weather: {result.meta.weather_source} · Routing: {result.meta.routing_source}. Truck times are car estimates ×{result.meta.truck_time_factor}; excludes breaks.</p>
            </section>
          )}

          {!busy && !result && !bannerError && <EmptyState />}
        </aside>

        <section className="map-area">
          <MapView
            result={result}
            selectedId={selectedId}
            focus={focus}
            heatmap={heat}
            heatHour={hour}
            heatVisible={heatVisible}
            onSelectRoute={setSelectedId}
            onFocusCheckpoint={focusCheckpoint}
          />
          <HeatmapControl
            status={heatStatus}
            data={heat}
            hour={hour}
            visible={heatVisible}
            onHour={setHour}
            onVisible={setHeatVisible}
            onRetry={() => result && lastReq.current && loadHeat(result, lastReq.current)}
          />
        </section>
      </main>
    </div>
  );
}

function titleFor(e: ApiError): string {
  switch (e.code) {
    case "NO_ROUTE":
      return "No route found";
    case "FORECAST_OUT_OF_RANGE":
      return "Forecast unavailable";
    case "NETWORK":
      return "You appear to be offline";
    case "TIMEOUT":
    case "UPSTREAM_TIMEOUT":
      return "Request timed out";
    case "RATE_LIMITED":
    case "UPSTREAM_RATE_LIMITED":
      return "Too many requests";
    default:
      return "We couldn't complete the analysis";
  }
}

function bannerMessage(e: ApiError): string {
  if (e.code !== "VALIDATION_ERROR") return e.message;
  return `The request was rejected. Check: ${Object.keys(e.fields).join(", ") || "your inputs"}.`;
}

function EmptyState() {
  return (
    <section className="card empty">
      <h2>How it works</h2>
      <ol>
        <li><b>Three routes</b> are generated between your origin and destination.</li>
        <li><b>Weather</b> is sampled every 10, 25 or 50 miles at the truck's estimated arrival time.</li>
        <li>Each checkpoint is scored for <b>wind, rain and snow</b>, adjusted for your <b>load weight</b>.</li>
        <li>We recommend the route that avoids No Travel conditions, then has the fewest Severe and High miles, the lowest average risk and the shortest time.</li>
      </ol>
    </section>
  );
}

function LoadingSkeleton() {
  return (
    <div className="results" aria-busy="true" aria-label="Analyzing routes">
      <div className="skeleton h80" />
      <div className="skeleton h120" />
      <div className="skeleton h120" />
      <div className="skeleton h120" />
    </div>
  );
}
