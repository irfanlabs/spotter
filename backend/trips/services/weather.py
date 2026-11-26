"""Hourly weather from Open-Meteo (keyless).

For every requested point we fetch an hourly series of wind (mph), rain and
snowfall (in/hr). Series are cached per ~1 km cell so repeated and overlapping
requests (route analysis + heatmap) stay cheap and polite to the provider.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.cache import cache

from ..exceptions import ForecastOutOfRange, UpstreamError
from .http import get_json

CHUNK = 40  # coordinates per request (keeps URLs short)
MAX_FORECAST_DAYS = 16
CACHE_TTL = 15 * 60
VARIABLES = "wind_speed_10m,rain,snowfall"


@dataclass(frozen=True)
class Series:
    start: datetime  # UTC time of index 0
    wind: tuple[float | None, ...]
    rain: tuple[float | None, ...]
    snow: tuple[float | None, ...]

    def index_for(self, when: datetime) -> int:
        """Nearest hourly index for `when`; raises if outside the forecast."""
        hours = (when - self.start).total_seconds() / 3600
        idx = round(hours)
        if idx < 0 or idx >= len(self.wind):
            raise ForecastOutOfRange()
        return idx

    def at(self, when: datetime) -> tuple[float, float, float]:
        i = self.index_for(when)
        values = self.wind[i], self.rain[i], self.snow[i]
        if None in values:
            # Missing data must never be mistaken for calm weather.
            raise ForecastOutOfRange("The weather forecast has no data for part of this time window.")
        return values


def _cell(lat: float, lon: float) -> tuple[float, float]:
    return round(lat, 2), round(lon, 2)


TIERS = (3, 7, MAX_FORECAST_DAYS)


def _tier(days: int) -> int:
    return next((t for t in TIERS if days <= t), MAX_FORECAST_DAYS)


def _num(v) -> float | None:
    """Open-Meteo reports gaps as null; keep them distinct from zero."""
    return float(v) if isinstance(v, (int, float)) else None


def forecast_horizon() -> datetime:
    """Latest moment a forecast can be requested for."""
    return datetime.now(timezone.utc) + timedelta(days=MAX_FORECAST_DAYS - 1)


def _parse(entry: dict) -> Series:
    try:
        hourly = entry["hourly"]
        times = hourly["time"]
        start = datetime.fromisoformat(times[0]).replace(tzinfo=timezone.utc)
        return Series(
            start,
            tuple(_num(v) for v in hourly["wind_speed_10m"]),
            tuple(_num(v) for v in hourly["rain"]),
            tuple(_num(v) for v in hourly["snowfall"]),
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise UpstreamError("Weather service returned an unexpected response.") from exc


def _fetch_chunk(cells: list[tuple[float, float]], days: int) -> list[Series]:
    data = get_json(
        f"{settings.OPEN_METEO_URL}/v1/forecast",
        params={
            "latitude": ",".join(f"{c[0]:.2f}" for c in cells),
            "longitude": ",".join(f"{c[1]:.2f}" for c in cells),
            "hourly": VARIABLES,
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "UTC",
            "past_days": 1,
            "forecast_days": days,
        },
        provider="Weather service",
        timeout=settings.WEATHER_TIMEOUT,
        ok_statuses=(200,),
    )
    entries = data if isinstance(data, list) else [data]
    if len(entries) != len(cells):
        raise UpstreamError("Weather service returned an unexpected number of locations.")
    return [_parse(e) for e in entries]


def fetch_series(points: list[tuple[float, float]], needed_until: datetime) -> list[Series]:
    """Series for each point (same order). `needed_until` sizes the forecast window."""
    now = datetime.now(timezone.utc)
    ahead_days = (needed_until - now).total_seconds() / 86400
    if ahead_days > MAX_FORECAST_DAYS - 1:
        raise ForecastOutOfRange(
            f"Weather forecasts only extend {MAX_FORECAST_DAYS - 1} days ahead; this trip ends after that."
        )
    days = _tier(max(1, math.ceil(ahead_days) + 1))
    larger_tiers = [t for t in TIERS if t >= days]

    cells = [_cell(*p) for p in points]
    found: dict[tuple[float, float], Series] = {}
    missing: list[tuple[float, float]] = []
    for c in dict.fromkeys(cells):
        # A cached longer forecast satisfies a shorter request.
        hit = next((h for t in larger_tiers if (h := cache.get(f"wx:{c[0]:.2f},{c[1]:.2f}:{t}"))), None)
        if hit:
            found[c] = hit
        else:
            missing.append(c)

    if missing:
        chunks = [missing[i : i + CHUNK] for i in range(0, len(missing), CHUNK)]
        with ThreadPoolExecutor(max_workers=min(4, len(chunks))) as pool:
            results = list(pool.map(lambda ch: _fetch_chunk(ch, days), chunks))
        for chunk, series_list in zip(chunks, results):
            for c, s in zip(chunk, series_list):
                found[c] = s
                cache.set(f"wx:{c[0]:.2f},{c[1]:.2f}:{days}", s, CACHE_TTL)

    return [found[c] for c in cells]
