from datetime import datetime, timedelta, timezone

import pytest
from django.core.cache import cache
from django.test import Client

from trips import exceptions
from trips.domain import geo
from trips.services import analysis, geocoding, routing, weather


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


def payload(**over):
    dep = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    base = {
        "origin": {"label": "Chicago, IL", "lat": 41.8781, "lon": -87.6298},
        "destination": {"label": "Dallas, TX", "lat": 32.7767, "lon": -96.797},
        "departure": dep,
        "load_weight_lb": 38000,
    }
    base.update(over)
    return base


def post(path, body):
    return Client().post(path, body, content_type="application/json")


def test_health():
    assert Client().get("/api/health").json() == {"status": "ok"}


def test_unknown_api_route_json_404():
    r = Client().get("/api/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "over,field",
    [
        ({"load_weight_lb": -1}, "load_weight_lb"),
        ({"load_weight_lb": 120000}, "load_weight_lb"),
        ({"departure": "2020-01-01T00:00:00Z"}, "departure"),
        ({"departure": "not-a-date"}, "departure"),
        ({"origin": {"label": "x", "lat": 200, "lon": 0}}, "origin"),
        ({"interval_miles": 7}, "interval_miles"),
        ({"destination": {"label": "Same", "lat": 41.8781, "lon": -87.6298}}, "destination"),
    ],
)
def test_validation_errors_are_structured(over, field):
    r = post("/api/analyze", payload(**over))
    body = r.json()
    assert r.status_code == 400
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert field in body["error"]["details"]["fields"]


def test_departure_without_timezone_is_rejected():
    naive = (datetime.now(timezone.utc) + timedelta(hours=3)).replace(tzinfo=None).isoformat()
    r = post("/api/analyze", payload(departure=naive))
    assert r.status_code == 400
    assert "timezone" in r.json()["error"]["details"]["fields"]["departure"][0]


@pytest.mark.parametrize(
    "exc,status,code",
    [
        (exceptions.NoRouteFound(), 422, "NO_ROUTE"),
        (exceptions.UpstreamTimeout(), 504, "UPSTREAM_TIMEOUT"),
        (exceptions.UpstreamError(), 502, "UPSTREAM_ERROR"),
        (exceptions.UpstreamRateLimited(), 503, "UPSTREAM_RATE_LIMITED"),
        (exceptions.ForecastOutOfRange(), 422, "FORECAST_OUT_OF_RANGE"),
    ],
)
def test_upstream_failures_map_to_clean_errors(monkeypatch, exc, status, code):
    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(routing, "generate_routes", boom)
    r = post("/api/analyze", payload())
    assert r.status_code == status and r.json()["error"]["code"] == code


def test_unexpected_exception_returns_500_without_leaking(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret internals")

    monkeypatch.setattr(analysis, "analyze", boom)
    c = Client(raise_request_exception=False)
    r = c.post("/api/analyze", payload(), content_type="application/json")
    assert r.status_code == 500
    assert "secret" not in r.content.decode() and r.json()["error"]["code"] == "INTERNAL_ERROR"


def test_geocode_short_query_and_results(monkeypatch):
    assert Client().get("/api/geocode?q=a").json() == {"results": []}
    monkeypatch.setattr(geocoding, "search", lambda q: [geocoding.Place("Chicago, Illinois, United States", 41.87, -87.62)])
    assert Client().get("/api/geocode?q=chicago").json()["results"][0]["label"].startswith("Chicago")


def test_geocode_strict_not_found(monkeypatch):
    monkeypatch.setattr(geocoding, "search", lambda q: [])
    r = Client().get("/api/geocode?q=zzzzzz&strict=1")
    assert r.status_code == 404 and r.json()["error"]["code"] == "PLACE_NOT_FOUND"


def test_heatmap_endpoint(monkeypatch):
    path = [(40.0, -100.0 + i * 0.2) for i in range(60)]
    dep = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    def fake_fetch(points, until):
        return [weather.Series(dep - timedelta(hours=24), (30.0,) * 400, (0.0,) * 400, (0.0,) * 400) for _ in points]

    monkeypatch.setattr(weather, "fetch_series", fake_fetch)
    r = post("/api/heatmap", {"geometries": [geo.encode_polyline(path)], "departure": (dep + timedelta(hours=1)).isoformat(), "load_weight_lb": 20000})
    assert r.status_code == 200
    body = r.json()
    assert body["hours"] == 48 and body["cells"]
    assert len(body["cells"][0]["levels"]) == 49 and set(body["cells"][0]["levels"]) == {1}  # 30 mph = Moderate


def test_heatmap_bad_geometry():
    r = post("/api/heatmap", {"geometries": [""], "departure": datetime.now(timezone.utc).isoformat(), "load_weight_lb": 1})
    assert r.status_code == 400
