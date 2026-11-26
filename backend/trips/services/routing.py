"""Route generation via OSRM.

OSRM's `alternatives` often returns only 1-2 routes. To offer three whenever
the road network allows, we top up with "via" routes: the origin->destination line is nudged sideways at
its midpoint and OSRM routes through that waypoint. Candidates that merely
retrace an existing route or are absurdly long are discarded.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from functools import cached_property

from django.conf import settings

from ..domain import geo
from ..exceptions import NoRouteFound, UpstreamError
from .http import get_json

logger = logging.getLogger(__name__)

MAX_DETOUR_RATIO = 1.6  # reject candidates >60% longer than the fastest
MIN_DISTINCTNESS = 0.80  # reject candidates overlapping an existing route by more than this
VIA_OFFSET_FRACTIONS = (0.14, 0.26)
TARGET_ROUTES = 3
VIA_WORKERS = 2  # public routing servers throttle bursts of requests
VIA_BUDGET_S = 20.0  # longest a response waits for extra route options


@dataclass
class RawRoute:
    path: list[geo.LatLon]  # full-resolution geometry
    distance_mi: float
    duration_s: float  # provider (car) duration, before truck adjustment

    @cached_property
    def cum(self) -> list[float]:
        """Cumulative miles along the path, computed once."""
        return geo.cumulative_miles(self.path)


def _osrm(coords: list[geo.LatLon], *, alternatives: bool) -> list[RawRoute]:
    coord_str = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in coords)
    data = get_json(
        f"{settings.OSRM_URL}/route/v1/driving/{coord_str}",
        params={
            "alternatives": "true" if alternatives else "false",
            "overview": "full",
            "geometries": "polyline6",
            "steps": "false",
            "continue_straight": "true",
        },
        provider="Routing service",
        timeout=settings.ROUTING_TIMEOUT,
        ok_statuses=(200, 400),
    )
    code = data.get("code") if isinstance(data, dict) else None
    if code == "NoRoute":
        raise NoRouteFound()
    if code in ("NoSegment", "InvalidQuery", "InvalidValue"):
        raise NoRouteFound("One of the locations is too far from a drivable road.")
    if code != "Ok":
        raise UpstreamError("Routing service returned an unexpected response.", details={"osrm_code": code})
    out = []
    for r in data.get("routes", []):
        try:
            out.append(RawRoute(geo.decode_polyline(r["geometry"], 6), r["distance"] / geo.METERS_PER_MILE, float(r["duration"])))
        except (KeyError, ValueError, TypeError) as exc:
            raise UpstreamError("Routing service returned a malformed route.") from exc
    return out


def _distinct(candidate: RawRoute, existing: list[RawRoute]) -> bool:
    def overlap(a: RawRoute, b: RawRoute) -> float:
        return geo.path_similarity(a.path, b.path, a_cum=a.cum, b_cum=b.cum)

    return all(overlap(candidate, e) < MIN_DISTINCTNESS and overlap(e, candidate) < MIN_DISTINCTNESS for e in existing)


def _via_candidates(origin: geo.LatLon, dest: geo.LatLon) -> list[RawRoute]:
    straight = geo.haversine_mi(origin, dest)
    mid = geo.interpolate(origin, dest, 0.5)
    brg = geo.bearing_deg(origin, dest)
    vias = [geo.destination_point(mid, (brg + side) % 360, straight * frac) for frac in VIA_OFFSET_FRACTIONS for side in (90, 270)]

    def one(via: geo.LatLon) -> RawRoute | None:
        try:
            routes = _osrm([origin, via, dest], alternatives=False)
            return routes[0] if routes else None
        except (NoRouteFound, UpstreamError) as exc:
            logger.info("via candidate failed: %s", exc)
            return None

    pool = ThreadPoolExecutor(max_workers=VIA_WORKERS)
    futures = [pool.submit(one, via) for via in vias]
    done, pending = wait(futures, timeout=VIA_BUDGET_S)
    # Extra options are a bonus: never hold the whole response for stragglers.
    pool.shutdown(wait=False, cancel_futures=True)
    if pending:
        logger.warning("Skipped %d slow extra-route request(s) after %.0fs", len(pending), VIA_BUDGET_S)
    return [route for f in futures if f in done and (route := f.result())]


def generate_routes(origin: geo.LatLon, dest: geo.LatLon) -> list[RawRoute]:
    if geo.haversine_mi(origin, dest) < 0.2:
        raise NoRouteFound("Origin and destination are the same place.")

    base = _osrm([origin, dest], alternatives=True)
    if not base:
        raise NoRouteFound()
    base.sort(key=lambda r: r.duration_s)
    fastest = base[0]

    chosen: list[RawRoute] = [fastest]
    for r in base[1:]:
        if len(chosen) < TARGET_ROUTES and _distinct(r, chosen):
            chosen.append(r)

    if len(chosen) < TARGET_ROUTES:
        candidates = [c for c in _via_candidates(origin, dest) if c.distance_mi <= fastest.distance_mi * MAX_DETOUR_RATIO]
        candidates.sort(key=lambda r: r.duration_s)
        for c in candidates:
            if len(chosen) >= TARGET_ROUTES:
                break
            if _distinct(c, chosen):
                chosen.append(c)

    if len(chosen) < TARGET_ROUTES:
        logger.info("Only %d distinct route(s) available", len(chosen))
    return chosen
