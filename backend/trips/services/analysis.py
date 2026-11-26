"""Orchestrates routing + weather + risk into the analyze / heatmap responses."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from django.conf import settings

from ..domain import geo, recommend, risk
from ..exceptions import ForecastOutOfRange
from . import routing, weather

MAX_CHECKPOINTS_PER_ROUTE = 120
DISPLAY_POINTS = 1500
ROUTE_NAMES = "ABC"
HEATMAP_HOURS = 48
HEATMAP_MAX_CELLS = 180
NO_FORECAST = -1  # heatmap level for hours with no forecast data


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float

    @property
    def latlon(self) -> geo.LatLon:
        return (self.lat, self.lon)


def auto_interval(distance_mi: float) -> int:
    if distance_mi <= 200:
        return 10
    if distance_mi <= 800:
        return 25
    return 50


def checkpoint_miles(total_mi: float, interval: float) -> list[float]:
    """Origin, every `interval` miles, then the destination. Interval is
    widened if needed to stay under the per-route cap."""
    interval = max(interval, total_mi / (MAX_CHECKPOINTS_PER_ROUTE - 1))
    marks = [0.0]
    m = interval
    while m < total_mi - interval * 0.25:  # avoid a tiny last hop before the destination
        marks.append(m)
        m += interval
    marks.append(total_mi)
    return marks


def _segment_weights(marks: list[float]) -> list[float]:
    """Miles of road each checkpoint is responsible for (midpoint to midpoint)."""
    n = len(marks)
    if n == 1:
        return [0.0]
    out = []
    for i in range(n):
        lo = marks[0] if i == 0 else (marks[i - 1] + marks[i]) / 2
        hi = marks[-1] if i == n - 1 else (marks[i] + marks[i + 1]) / 2
        out.append(hi - lo)
    return out


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def analyze(origin: Place, destination: Place, departure: datetime, load_lb: float, interval_opt: int | None) -> dict:
    raw_routes = routing.generate_routes(origin.latlon, destination.latlon)

    prepared = []
    for idx, raw in enumerate(raw_routes):
        cum = geo.cumulative_miles(raw.path)
        scale = raw.distance_mi / cum[-1] if cum[-1] else 1.0
        duration_s = raw.duration_s * settings.TRUCK_TIME_FACTOR
        # Report the spacing actually used: very long routes are capped and widened.
        interval = max(interval_opt or auto_interval(raw.distance_mi), raw.distance_mi / (MAX_CHECKPOINTS_PER_ROUTE - 1))
        marks = checkpoint_miles(raw.distance_mi, interval)
        pts = [geo.point_at(raw.path, cum, m / scale)[0] for m in marks]
        prepared.append({"idx": idx, "raw": raw, "duration_s": duration_s, "marks": marks, "pts": pts, "interval": interval})

    latest_arrival = max(departure + timedelta(seconds=p["duration_s"]) for p in prepared) + timedelta(hours=1)
    flat_points = [pt for p in prepared for pt in p["pts"]]
    series = weather.fetch_series(flat_points, latest_arrival)
    cursor = 0

    routes_out: list[dict] = []
    scores: dict[str, recommend.RouteScore] = {}
    for p in prepared:
        raw, marks = p["raw"], p["marks"]
        rid = f"route-{ROUTE_NAMES[p['idx']]}"
        weights = _segment_weights(marks)
        cps_out, cps_dom = [], []
        for i, (mile, pt) in enumerate(zip(marks, p["pts"])):
            s = series[cursor + i]
            eta = departure + timedelta(seconds=p["duration_s"] * (mile / raw.distance_mi if raw.distance_mi else 0))
            wind, rain, snow = s.at(eta)
            a = risk.assess(wind, rain, snow, load_lb)
            cps_dom.append(recommend.Checkpoint(mile, weights[i], a.level))
            cps_out.append(
                {
                    "index": i,
                    "lat": round(pt[0], 5),
                    "lon": round(pt[1], 5),
                    "mile": round(mile, 1),
                    "eta": _iso(eta),
                    "segment_miles": round(weights[i], 1),
                    "weather": {"wind_mph": round(wind, 1), "rain_in_hr": round(rain, 3), "snow_in_hr": round(snow, 2)},
                    "risk": a.as_dict(),
                }
            )
        cursor += len(marks)

        score = recommend.score_route(cps_dom, raw.distance_mi, p["duration_s"])
        scores[rid] = score
        display = geo.simplify_to_budget(raw.path, DISPLAY_POINTS)
        routes_out.append(
            {
                "id": rid,
                "name": f"Route {ROUTE_NAMES[p['idx']]}",
                "geometry": geo.encode_polyline(display),
                "distance_mi": round(raw.distance_mi, 1),
                "duration_s": round(p["duration_s"]),
                "departure": _iso(departure),
                "arrival": _iso(departure + timedelta(seconds=p["duration_s"])),
                "interval_miles": round(p["interval"], 1),
                "miles_by_level": score.miles_by_level,
                "avg_risk": round(score.avg_risk, 2),
                "max_level": int(score.max_level),
                "max_level_label": score.max_level.label,
                "checkpoints": cps_out,
            }
        )

    ranking = recommend.rank(scores)
    names = {r["id"]: r["name"] for r in routes_out}
    fastest = min(routes_out, key=lambda r: r["duration_s"])["id"]
    shortest = min(routes_out, key=lambda r: r["distance_mi"])["id"]
    for r in routes_out:
        r["rank"] = ranking.index(r["id"]) + 1
        r["recommended"] = r["rank"] == 1
        r["tags"] = [t for t, rid in (("Fastest", fastest), ("Shortest", shortest)) if rid == r["id"]]
        r["summary"] = _summary(r, scores[r["id"]])
    routes_out.sort(key=lambda r: r["rank"])

    best = ranking[0]
    return {
        "request": {
            "origin": {"label": origin.label, "lat": origin.lat, "lon": origin.lon},
            "destination": {"label": destination.label, "lat": destination.lat, "lon": destination.lon},
            "departure": _iso(departure),
            "load_weight_lb": load_lb,
        },
        "recommendation": {
            "route_id": best,
            "route_name": names[best],
            "reasons": recommend.explain(best, scores, names),
            "travel_advised": scores[best].miles_by_level["no_travel"] == 0,
        },
        "routes": routes_out,
        "meta": {
            "generated_at": _iso(datetime.now(timezone.utc)),
            "weather_source": "Open-Meteo",
            "routing_source": "OSRM / OpenStreetMap",
            "truck_time_factor": settings.TRUCK_TIME_FACTOR,
        },
    }


def _fmt_duration(seconds: float) -> str:
    minutes = int(round(seconds / 60))
    h, m = divmod(minutes, 60)
    return f"{h} hr {m:02d} min" if h else f"{m} min"


def _summary(route: dict, score: recommend.RouteScore) -> str:
    m = score.miles_by_level
    head = f"{route['distance_mi']:,.0f} mi, {_fmt_duration(route['duration_s'])}."
    if m["no_travel"] > 0:
        body = f"{m['no_travel']:.0f} mi of No Travel conditions."
    elif m["severe"] > 0:
        body = f"{m['severe']:.0f} mi Severe, {m['high']:.0f} mi High."
    elif m["high"] > 0:
        body = f"{m['high']:.0f} mi of High risk, no Severe segments."
    elif m["moderate"] > 0:
        body = f"{m['moderate']:.0f} mi of Moderate weather, nothing worse."
    else:
        body = "Clear conditions throughout."
    return f"{head} {body}"


# ---------------------------------------------------------------- heatmap

def corridor_cells(paths: list[list[geo.LatLon]], spacing_mi: float, offset_mi: float) -> tuple[list[geo.LatLon], float]:
    """A de-duplicated lattice of points along and either side of every route.

    Spacing widens until the lattice fits the cell budget. Returns the cells and
    the spacing finally used, so the map can size each cell to leave no gaps."""
    while True:
        cell_deg = spacing_mi / 69.0
        seen: dict[tuple[int, int], geo.LatLon] = {}
        for path in paths:
            cum = geo.cumulative_miles(path)
            total = cum[-1]
            n = max(1, math.ceil(total / spacing_mi))
            for k in range(n + 1):
                pt, seg = geo.point_at(path, cum, min(total, k * spacing_mi))
                brg = geo.bearing_deg(path[seg], path[min(seg + 1, len(path) - 1)])
                for off in (-offset_mi, 0.0, offset_mi):
                    q = pt if off == 0 else geo.destination_point(pt, (brg + (90 if off > 0 else 270)) % 360, abs(off))
                    key = (round(q[0] / cell_deg), round(q[1] / (cell_deg / max(0.2, math.cos(math.radians(q[0]))))))
                    seen.setdefault(key, q)
        if len(seen) <= HEATMAP_MAX_CELLS or spacing_mi > 400:
            return list(seen.values()), spacing_mi
        spacing_mi *= 1.25
        offset_mi *= 1.1


def heatmap(paths: list[list[geo.LatLon]], departure: datetime, load_lb: float) -> dict:
    start = departure.replace(minute=0, second=0, microsecond=0)
    cells, spacing_mi = corridor_cells(paths, spacing_mi=25.0, offset_mi=18.0)
    # Late departures can reach past the forecast horizon: fetch what exists.
    needed_until = min(start + timedelta(hours=HEATMAP_HOURS + 1), weather.forecast_horizon())
    series = weather.fetch_series(cells, needed_until)

    out = []
    for (lat, lon), s in zip(cells, series):
        levels, wind, rain, snow = [], [], [], []
        for h in range(HEATMAP_HOURS + 1):
            try:
                w, r, sn = s.at(start + timedelta(hours=h))
                level = int(risk.assess(w, r, sn, load_lb).level)
            except ForecastOutOfRange:
                w = r = sn = 0.0
                level = NO_FORECAST
            levels.append(level)
            wind.append(round(w))
            rain.append(round(r, 2))
            snow.append(round(sn, 1))
        out.append({"lat": round(lat, 4), "lon": round(lon, 4), "levels": levels, "wind": wind, "rain": rain, "snow": snow})

    return {
        "start": _iso(start),
        "hours": HEATMAP_HOURS,
        "cell_radius_mi": round(spacing_mi * 0.75),
        "cells": out,
    }
