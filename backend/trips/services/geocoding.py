"""Place search via Photon (OSM data, keyless, built for autocomplete)."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

from ..exceptions import UpstreamError
from .http import get_json


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float

    def as_dict(self) -> dict:
        return {"label": self.label, "lat": self.lat, "lon": self.lon}


def _label(props: dict) -> str:
    name = props.get("name") or props.get("street") or ""
    street = ""
    if props.get("street") and props.get("name") != props.get("street"):
        street = f"{props.get('housenumber', '')} {props['street']}".strip()
    parts = [name, street, props.get("city") if props.get("city") != name else None, props.get("state"), props.get("country")]
    seen: list[str] = []
    for p in parts:
        if p and p not in seen:
            seen.append(p)
    return ", ".join(seen)


def search(query: str, limit: int = 6) -> list[Place]:
    q = " ".join(query.split())
    if len(q) < 2:
        return []
    key = f"geo:{q.lower()}:{limit}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    data = get_json(
        f"{settings.PHOTON_URL}/api/",
        params={"q": q, "limit": limit, "lang": "en"},
        provider="Geocoding service",
        timeout=settings.GEOCODING_TIMEOUT,
    )
    try:
        features = data["features"]
        places = []
        for f in features:
            lon, lat = f["geometry"]["coordinates"][:2]
            label = _label(f.get("properties", {}))
            if label:
                places.append(Place(label, round(lat, 6), round(lon, 6)))
    except (KeyError, TypeError, ValueError) as exc:
        raise UpstreamError("Geocoding service returned an unexpected response.") from exc

    # De-duplicate identical labels, keep order.
    uniq: dict[str, Place] = {}
    for p in places:
        uniq.setdefault(p.label, p)
    result = list(uniq.values())
    cache.set(key, result, 60 * 60)
    return result
