import { useState } from "react";
import { ApiError, searchPlaces } from "../api";
import { defaultDeparture } from "../lib/format";
import { MAX_LOAD, parseLoad, validate, type FieldErrors } from "../lib/validation";
import type { AnalyzeRequest, Place } from "../types";
import { IconRoute, IconSwap } from "./Icons";
import { PlaceInput } from "./PlaceInput";

const PRESETS = [
  { label: "Empty", lb: 10_000 },
  { label: "Medium", lb: 30_000 },
  { label: "Heavy", lb: 40_000 },
  { label: "Max", lb: 80_000 },
];

interface Props {
  busy: boolean;
  serverFieldErrors: FieldErrors;
  onSubmit: (req: AnalyzeRequest) => void;
}

export function TripForm({ busy, serverFieldErrors, onSubmit }: Props) {
  const [originText, setOriginText] = useState("");
  const [destText, setDestText] = useState("");
  const [origin, setOrigin] = useState<Place | null>(null);
  const [dest, setDest] = useState<Place | null>(null);
  const [departure, setDeparture] = useState(defaultDeparture);
  const [load, setLoad] = useState("38,000");
  const [spacing, setSpacing] = useState<"auto" | "10" | "25" | "50">("auto");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [resolving, setResolving] = useState(false);

  const shown = { ...serverFieldErrors, ...errors };

  const swap = () => {
    setOriginText(destText);
    setDestText(originText);
    setOrigin(dest);
    setDest(origin);
  };

  /** If the user typed without picking a suggestion, resolve the top geocoding match.
   *  Returns null when the place doesn't exist and throws if the search itself fails. */
  const resolve = async (text: string, current: Place | null): Promise<Place | null> => {
    if (current) return current;
    try {
      const { results } = await searchPlaces(text.trim(), undefined, true);
      return results[0] ?? null;
    } catch (e) {
      if (e instanceof ApiError && e.code === "PLACE_NOT_FOUND") return null;
      throw e;
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const v = { originText, destText, departure, load };
    const errs = validate(v, !!origin, !!dest);
    setErrors(errs);
    if (Object.keys(errs).length) return;

    setResolving(true);
    try {
      const [o, d] = await Promise.all([resolve(originText, origin), resolve(destText, dest)]);
      const next: FieldErrors = {};
      if (!o) next.origin = `We couldn't find “${originText}”. Try adding a city or state.`;
      if (!d) next.destination = `We couldn't find “${destText}”. Try adding a city or state.`;
      if (next.origin || next.destination) return setErrors(next);
      if (!origin && o) {
        setOrigin(o);
        setOriginText(o.label);
      }
      if (!dest && d) {
        setDest(d);
        setDestText(d.label);
      }
      onSubmit({
        origin: o!,
        destination: d!,
        departure: new Date(departure).toISOString(),
        load_weight_lb: parseLoad(load),
        interval_miles: spacing === "auto" ? null : (Number(spacing) as 10 | 25 | 50),
      });
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "Location search is unavailable right now. Please try again.";
      setErrors({ ...(origin ? {} : { origin: message }), ...(dest ? {} : { destination: message }) });
    } finally {
      setResolving(false);
    }
  };

  const loadNum = parseLoad(load);
  const loading = busy || resolving;

  return (
    <form className="card form" onSubmit={submit} noValidate>
      <div className="places">
        <div className="places-fields">
          <PlaceInput
            label="Origin"
            placeholder="City, address or place"
            value={originText}
            place={origin}
            error={shown.origin}
            onText={(t) => {
              setOriginText(t);
              setErrors((x) => ({ ...x, origin: undefined }));
            }}
            onPlace={setOrigin}
          />
          <PlaceInput
            label="Destination"
            placeholder="City, address or place"
            value={destText}
            place={dest}
            error={shown.destination}
            onText={(t) => {
              setDestText(t);
              setErrors((x) => ({ ...x, destination: undefined }));
            }}
            onPlace={setDest}
          />
        </div>
        <button type="button" className="icon-btn swap" onClick={swap} aria-label="Swap origin and destination" title="Swap">
          <IconSwap />
        </button>
      </div>

      <div className="row">
        <div className="field">
          <label htmlFor="departure">Departure</label>
          <div className={`input-wrap ${shown.departure ? "has-error" : ""}`}>
            <input
              id="departure"
              type="datetime-local"
              value={departure}
              aria-invalid={!!shown.departure}
              onChange={(e) => {
                setDeparture(e.target.value);
                setErrors((x) => ({ ...x, departure: undefined }));
              }}
            />
          </div>
          {shown.departure && <p className="field-error">{shown.departure}</p>}
        </div>
        <div className="field">
          <label htmlFor="load">Load weight (lb)</label>
          <div className={`input-wrap ${shown.load ? "has-error" : ""}`}>
            <input
              id="load"
              inputMode="numeric"
              value={load}
              aria-invalid={!!shown.load}
              onChange={(e) => {
                setLoad(e.target.value);
                setErrors((x) => ({ ...x, load: undefined }));
              }}
              onBlur={() => {
                const n = parseLoad(load);
                if (Number.isFinite(n) && load.trim()) setLoad(n.toLocaleString());
              }}
            />
          </div>
          {shown.load && <p className="field-error">{shown.load}</p>}
        </div>
      </div>

      <div className="chips" role="group" aria-label="Load presets">
        {PRESETS.map((p) => (
          <button
            key={p.lb}
            type="button"
            className={`chip ${loadNum === p.lb ? "on" : ""}`}
            onClick={() => {
              setLoad(p.lb.toLocaleString());
              setErrors((x) => ({ ...x, load: undefined }));
            }}
          >
            {p.label} <span>{(p.lb / 1000).toFixed(0)}k</span>
          </button>
        ))}
      </div>
      <input
        className="range"
        type="range"
        min={0}
        max={MAX_LOAD}
        step={1000}
        value={Number.isFinite(loadNum) ? Math.min(MAX_LOAD, Math.max(0, loadNum)) : 0}
        onChange={(e) => setLoad(Number(e.target.value).toLocaleString())}
        aria-label="Load weight slider"
      />

      <div className="field">
        <label htmlFor="interval">Weather checkpoints</label>
        <div className="input-wrap">
          <select id="interval" value={spacing} onChange={(e) => setSpacing(e.target.value as typeof spacing)}>
            <option value="auto">Auto (by trip length)</option>
            <option value="10">Every 10 miles</option>
            <option value="25">Every 25 miles</option>
            <option value="50">Every 50 miles</option>
          </select>
        </div>
      </div>

      <button className="btn btn-primary btn-block" type="submit" disabled={loading}>
        {loading ? (
          <>
            <span className="spinner" /> Finding routes and weather…
          </>
        ) : (
          <>
            <IconRoute /> Find safest route
          </>
        )}
      </button>
    </form>
  );
}
