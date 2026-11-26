from datetime import datetime, timedelta, timezone

import pytest

from trips.services import analysis, routing, weather


def test_checkpoint_miles_cover_route_and_cap():
    marks = analysis.checkpoint_miles(100, 25)
    assert marks[0] == 0 and marks[-1] == 100 and marks == sorted(marks)
    assert len(analysis.checkpoint_miles(3000, 10)) <= analysis.MAX_CHECKPOINTS_PER_ROUTE


def test_segment_weights_sum_to_total():
    marks = analysis.checkpoint_miles(137, 25)
    assert sum(analysis._segment_weights(marks)) == pytest.approx(137)


def test_auto_interval():
    assert (analysis.auto_interval(50), analysis.auto_interval(500), analysis.auto_interval(1500)) == (10, 25, 50)


def _straight():
    return routing.RawRoute([(40.0, -100.0 + i * 0.1) for i in range(0, 101)], 500.0, 7 * 3600)


def test_analyze_end_to_end_with_stubbed_providers(monkeypatch):
    dep = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    route_a = _straight()
    route_b = routing.RawRoute([(41.0, -100.0 + i * 0.1) for i in range(101)], 520.0, 7.5 * 3600)
    monkeypatch.setattr(routing, "generate_routes", lambda o, d: [route_a, route_b])

    def fake_fetch(points, needed_until):
        out = []
        for lat, _ in points:
            wind = 50.0 if round(lat) == 40 else 5.0  # route A is windy
            out.append(weather.Series(dep - timedelta(hours=24), (wind,) * 400, (0.0,) * 400, (0.0,) * 400))
        return out

    monkeypatch.setattr(weather, "fetch_series", fake_fetch)
    o = analysis.Place("A", 40.0, -100.0)
    d = analysis.Place("B", 40.0, -90.0)

    result = analysis.analyze(o, d, dep, 35_000, None)
    assert result["recommendation"]["route_id"] == "route-B"
    by_id = {r["id"]: r for r in result["routes"]}
    assert by_id["route-A"]["miles_by_level"]["no_travel"] > 0  # 50 mph + >30k lb
    assert by_id["route-B"]["miles_by_level"]["low"] == pytest.approx(520, abs=0.5)
    assert by_id["route-A"]["checkpoints"][0]["mile"] == 0
    assert by_id["route-A"]["checkpoints"][-1]["mile"] == 500
    assert result["routes"][0]["rank"] == 1

    # Light load: the same wind is only Severe, never No Travel.
    light = analysis.analyze(o, d, dep, 10_000, None)
    assert {r["id"]: r for r in light["routes"]}["route-A"]["miles_by_level"]["no_travel"] == 0


def test_eta_progresses_linearly(monkeypatch):
    dep = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    monkeypatch.setattr(routing, "generate_routes", lambda o, d: [_straight()])
    monkeypatch.setattr(
        weather, "fetch_series",
        lambda pts, until: [weather.Series(dep - timedelta(hours=24), (0.0,) * 400, (0.0,) * 400, (0.0,) * 400) for _ in pts],
    )
    r = analysis.analyze(analysis.Place("A", 40, -100), analysis.Place("B", 40, -90), dep, 1000, 50)["routes"][0]
    etas = [datetime.fromisoformat(c["eta"].replace("Z", "+00:00")) for c in r["checkpoints"]]
    assert etas == sorted(etas) and etas[0] == dep
    assert (etas[-1] - dep).total_seconds() == pytest.approx(r["duration_s"], abs=1)


def test_corridor_cells_are_capped_and_unique():
    path = [(40.0, -120.0 + i * 0.5) for i in range(100)]
    cells, spacing = analysis.corridor_cells([path, [(41, lon) for _, lon in path]], 25.0, 18.0)
    assert spacing >= 25.0
    assert 0 < len(cells) <= analysis.HEATMAP_MAX_CELLS
    assert len(set(cells)) == len(cells)
