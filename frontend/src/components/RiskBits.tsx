import { LEVELS, levelMeta } from "../lib/risk";
import type { MilesByLevel } from "../types";

export function RiskPill({ level, label }: { level: number; label?: string }) {
  const m = levelMeta(level);
  return (
    <span className="pill" style={{ background: m.soft, color: m.ink }}>
      <i style={{ background: m.color }} />
      {label ?? m.label}
    </span>
  );
}

/** Stacked bar of route miles by risk level, with an accessible text equivalent. */
export function RiskBar({ miles, total }: { miles: MilesByLevel; total: number }) {
  const desc = LEVELS.filter((l) => miles[l.key] > 0.5)
    .map((l) => `${Math.round(miles[l.key])} miles ${l.label}`)
    .join(", ");
  return (
    <div className="riskbar" role="img" aria-label={`Miles by risk: ${desc || "all low"}`}>
      {LEVELS.map((l) =>
        miles[l.key] > 0 ? (
          <span key={l.key} style={{ width: `${(miles[l.key] / total) * 100}%`, background: l.color }} title={`${l.label}: ${Math.round(miles[l.key])} mi`} />
        ) : null,
      )}
    </div>
  );
}

export function RiskLegend({ compact = false }: { compact?: boolean }) {
  return (
    <ul className={`legend ${compact ? "compact" : ""}`} aria-label="Risk levels">
      {LEVELS.map((l) => (
        <li key={l.key}>
          <i style={{ background: l.color }} />
          {l.label}
        </li>
      ))}
    </ul>
  );
}
