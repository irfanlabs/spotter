"""Geometry helpers: distances, polyline codec, sampling along a path."""

from __future__ import annotations

import math
from bisect import bisect_right
from typing import Sequence

EARTH_RADIUS_MI = 3958.7613
METERS_PER_MILE = 1609.344

LatLon = tuple[float, float]


def haversine_mi(a: LatLon, b: LatLon) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(min(1.0, math.sqrt(h)))


def cumulative_miles(path: Sequence[LatLon]) -> list[float]:
    out = [0.0]
    for i in range(1, len(path)):
        out.append(out[-1] + haversine_mi(path[i - 1], path[i]))
    return out


def decode_polyline(encoded: str, precision: int = 6) -> list[LatLon]:
    """Decode a Google/OSRM encoded polyline to [(lat, lon), ...]."""
    factor = 10**precision
    coords: list[LatLon] = []
    index = lat = lon = 0
    n = len(encoded)
    while index < n:
        for axis in (0, 1):
            shift = result = 0
            while True:
                if index >= n:
                    raise ValueError("Truncated polyline")
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += delta
            else:
                lon += delta
        coords.append((lat / factor, lon / factor))
    return coords


def encode_polyline(path: Sequence[LatLon], precision: int = 6) -> str:
    factor = 10**precision
    out: list[str] = []
    prev_lat = prev_lon = 0
    for lat, lon in path:
        ilat, ilon = round(lat * factor), round(lon * factor)
        for delta in (ilat - prev_lat, ilon - prev_lon):
            v = ~(delta << 1) if delta < 0 else delta << 1
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        prev_lat, prev_lon = ilat, ilon
    return "".join(out)


def interpolate(a: LatLon, b: LatLon, t: float) -> LatLon:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def point_at(path: Sequence[LatLon], cum: Sequence[float], miles: float) -> tuple[LatLon, int]:
    """Point `miles` along the path (clamped) and the index of the segment it lies on."""
    if miles <= 0:
        return path[0], 0
    if miles >= cum[-1]:
        return path[-1], max(0, len(path) - 2)
    i = bisect_right(cum, miles) - 1
    seg = cum[i + 1] - cum[i]
    t = 0.0 if seg == 0 else (miles - cum[i]) / seg
    return interpolate(path[i], path[i + 1], t), i


def bearing_deg(a: LatLon, b: LatLon) -> float:
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(b[1] - a[1])
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def destination_point(origin: LatLon, bearing: float, miles: float) -> LatLon:
    """Great-circle destination from origin along a bearing."""
    lat1, lon1 = math.radians(origin[0]), math.radians(origin[1])
    brg = math.radians(bearing)
    d = miles / EARTH_RADIUS_MI
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(brg))
    lon2 = lon1 + math.atan2(math.sin(brg) * math.sin(d) * math.cos(lat1), math.cos(d) - math.sin(lat1) * math.sin(lat2))
    return (math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180)


def simplify(path: Sequence[LatLon], tolerance_deg: float) -> list[LatLon]:
    """Iterative Ramer-Douglas-Peucker in lat/lon space (adequate for display)."""
    n = len(path)
    if n <= 2:
        return list(path)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    tol2 = tolerance_deg**2
    while stack:
        lo, hi = stack.pop()
        ax, ay = path[lo][1], path[lo][0]
        bx, by = path[hi][1], path[hi][0]
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        best, best_i = -1.0, -1
        for i in range(lo + 1, hi):
            px, py = path[i][1], path[i][0]
            if seg2 == 0:
                d2 = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
                d2 = (px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2
            if d2 > best:
                best, best_i = d2, i
        if best > tol2 and best_i != -1:
            keep[best_i] = True
            stack.append((lo, best_i))
            stack.append((best_i, hi))
    return [p for p, k in zip(path, keep) if k]


def simplify_to_budget(path: Sequence[LatLon], max_points: int) -> list[LatLon]:
    """Simplify with increasing tolerance until at most `max_points` remain."""
    tol = 0.0005
    out = list(path)
    while len(out) > max_points and tol < 1.0:
        out = simplify(path, tol)
        tol *= 1.6
    return out


def path_similarity(a: Sequence[LatLon], b: Sequence[LatLon], samples: int = 40, threshold_mi: float = 3.0) -> float:
    """Fraction of points sampled along `a` that lie within `threshold_mi` of path `b`."""
    ca, cb = cumulative_miles(a), cumulative_miles(b)
    if ca[-1] == 0 or cb[-1] == 0:
        return 1.0
    b_pts = [point_at(b, cb, cb[-1] * k / 199)[0] for k in range(200)]
    close = 0
    for k in range(samples):
        p = point_at(a, ca, ca[-1] * k / (samples - 1))[0]
        if min(haversine_mi(p, q) for q in b_pts) <= threshold_mi:
            close += 1
    return close / samples
