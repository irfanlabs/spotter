"""Route scoring and recommendation.

Order of preference (from the brief):
    1. fewest Severe miles
    2. fewest High miles
    3. lowest average risk
    4. shortest travel time

Two judgement calls, both documented in the README:
* No Travel is ranked *before* Severe. A route with any No Travel mileage can
  never beat a route without it; between two such routes, fewer miles wins.
* Mileage, risk and time are rounded to steps (5 miles, 0.1 risk points,
  1 minute) before comparing, so values that round to the same step fall through
  to the next criterion. This is how risk is balanced against travel time: a
  stray Severe mile on a long haul should not outweigh a 3-hour detour.
"""

from __future__ import annotations

from dataclasses import dataclass

from .risk import LEVEL_KEYS, RiskLevel

MILES_BUCKET = 5.0
RISK_BUCKET = 0.1
TIME_BUCKET_S = 60.0


@dataclass(frozen=True)
class Checkpoint:
    mile: float
    segment_miles: float
    level: RiskLevel


@dataclass(frozen=True)
class RouteScore:
    miles_by_level: dict[str, float]
    avg_risk: float
    max_level: RiskLevel
    duration_s: float
    distance_mi: float


def score_route(checkpoints: list[Checkpoint], distance_mi: float, duration_s: float) -> RouteScore:
    miles = {k: 0.0 for k in LEVEL_KEYS}
    weighted = 0.0
    total = 0.0
    for cp in checkpoints:
        miles[cp.level.key] += cp.segment_miles
        weighted += int(cp.level) * cp.segment_miles
        total += cp.segment_miles
    avg = weighted / total if total else 0.0
    max_level = max((cp.level for cp in checkpoints), default=RiskLevel.LOW)
    return RouteScore(
        {k: round(v, 1) for k, v in miles.items()}, round(avg, 3), max_level, duration_s, distance_mi
    )


def _bucket(value: float, size: float) -> int:
    return int(round(value / size))


def sort_key(score: RouteScore) -> tuple:
    m = score.miles_by_level
    return (
        m["no_travel"] > 0,  # presence first, however short the segment
        _bucket(m["no_travel"], MILES_BUCKET),
        _bucket(m["severe"], MILES_BUCKET),
        _bucket(m["high"], MILES_BUCKET),
        _bucket(score.avg_risk, RISK_BUCKET),
        _bucket(score.duration_s, TIME_BUCKET_S),
        # Exact values as final deterministic tiebreakers.
        m["no_travel"],
        m["severe"],
        m["high"],
        score.avg_risk,
        score.duration_s,
    )


def rank(scores: dict[str, RouteScore]) -> list[str]:
    return sorted(scores, key=lambda rid: sort_key(scores[rid]))


def explain(best_id: str, scores: dict[str, RouteScore], names: dict[str, str]) -> list[str]:
    """Human-readable reasons why `best_id` wins, comparing against the others."""
    best = scores[best_id]
    others = {rid: s for rid, s in scores.items() if rid != best_id}
    reasons: list[str] = []

    if not others:
        reasons.append("Only one drivable route was found between these locations.")
    else:
        fastest_id = min(scores, key=lambda r: scores[r].duration_s)
        for label, key in (("No Travel", "no_travel"), ("Severe", "severe"), ("High", "high")):
            mine = best.miles_by_level[key]
            worst_other = max(s.miles_by_level[key] for s in others.values())
            if worst_other - mine >= MILES_BUCKET:
                reasons.append(f"{mine:.0f} mi of {label} weather vs up to {worst_other:.0f} mi on alternatives")
            elif mine == 0 and key == "severe":
                reasons.append("No Severe weather along the route")
        lower_risk = [s for s in others.values() if s.avg_risk - best.avg_risk >= RISK_BUCKET]
        if lower_risk and not reasons:
            reasons.append(f"Lowest average risk score ({best.avg_risk:.2f} on a 0-4 scale)")
        if fastest_id == best_id:
            reasons.append("Also the fastest route")
        else:
            delta_min = (best.duration_s - scores[fastest_id].duration_s) / 60
            if delta_min >= 1:
                reasons.append(f"Adds {_fmt_minutes(delta_min)} compared with the fastest route")
        if not reasons:
            reasons.append("Routes are comparable on weather risk; this one is the quickest")

    if best.miles_by_level["no_travel"] > 0:
        reasons.insert(0, "Every route crosses a No Travel segment; this has the least exposure")
    return reasons


def _fmt_minutes(minutes: float) -> str:
    m = int(round(minutes))
    h, m = divmod(m, 60)
    if h and m:
        return f"{h} hr {m} min"
    return f"{h} hr" if h else f"{m} min"
