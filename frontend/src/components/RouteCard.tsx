import { formatDuration, formatMiles, formatShort } from "../lib/format";
import type { Route } from "../types";
import { RiskBar, RiskPill } from "./RiskBits";

interface Props {
  route: Route;
  selected: boolean;
  color: string;
  onSelect: () => void;
}

export function RouteCard({ route, selected, color, onSelect }: Props) {
  return (
    <button type="button" className={`route-card ${selected ? "selected" : ""}`} onClick={onSelect} aria-pressed={selected}>
      <div className="route-head">
        <span className="swatch" style={{ background: color }} />
        <strong>{route.name}</strong>
        {route.recommended && <span className="badge brand">Recommended</span>}
        {route.tags.map((t) => (
          <span key={t} className="badge">
            {t}
          </span>
        ))}
        <span className="grow" />
        <RiskPill level={route.max_level} label={`Peak: ${route.max_level_label}`} />
      </div>
      <dl className="metrics">
        <div>
          <dt>Time</dt>
          <dd>{formatDuration(route.duration_s)}</dd>
        </div>
        <div>
          <dt>Distance</dt>
          <dd>{formatMiles(route.distance_mi)}</dd>
        </div>
        <div>
          <dt>Arrive</dt>
          <dd>{formatShort(route.arrival)}</dd>
        </div>
        <div>
          <dt>Avg risk</dt>
          <dd>{route.avg_risk.toFixed(2)}<small>/4</small></dd>
        </div>
      </dl>
      <RiskBar miles={route.miles_by_level} total={route.distance_mi} />
      <p className="summary">{route.summary}</p>
    </button>
  );
}
