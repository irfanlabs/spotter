from trips.domain.recommend import Checkpoint, explain, rank, score_route
from trips.domain.risk import RiskLevel as L


def route(levels, distance=100.0, duration=3600.0):
    n = len(levels)
    seg = distance / n
    cps = [Checkpoint(i * seg, seg, lvl) for i, lvl in enumerate(levels)]
    return score_route(cps, distance, duration)


def test_miles_sum_to_distance_and_average():
    s = route([L.LOW, L.HIGH, L.SEVERE, L.LOW])
    assert sum(s.miles_by_level.values()) == 100.0
    assert s.miles_by_level["high"] == 25.0
    assert s.avg_risk == (0 + 2 + 3 + 0) / 4
    assert s.max_level == L.SEVERE


def test_fewest_severe_miles_wins_over_speed():
    safe_slow = route([L.LOW] * 10, duration=9000)
    fast_severe = route([L.SEVERE] * 5 + [L.LOW] * 5, duration=3000)
    assert rank({"a": fast_severe, "b": safe_slow}) == ["b", "a"]


def test_no_travel_ranks_before_severe():
    nt = route([L.NO_TRAVEL] + [L.LOW] * 9)
    sev = route([L.SEVERE] * 5 + [L.LOW] * 5)
    assert rank({"nt": nt, "sev": sev})[0] == "sev"


def test_even_a_short_no_travel_stretch_loses():
    short_nt = route([L.NO_TRAVEL, L.LOW], distance=4.0)
    severe = route([L.SEVERE, L.SEVERE], distance=4.0)
    assert rank({"nt": short_nt, "sev": severe}) == ["sev", "nt"]


def test_high_miles_break_severe_ties():
    a = route([L.HIGH] * 4 + [L.LOW] * 6)
    b = route([L.HIGH] * 2 + [L.LOW] * 8)
    assert rank({"a": a, "b": b}) == ["b", "a"]


def test_avg_risk_then_duration():
    a = route([L.MODERATE] * 5 + [L.LOW] * 5, duration=4000)
    b = route([L.MODERATE] * 1 + [L.LOW] * 9, duration=5000)
    assert rank({"a": a, "b": b}) == ["b", "a"]
    c = route([L.LOW] * 10, duration=4000)
    d = route([L.LOW] * 10, duration=3000)
    assert rank({"c": c, "d": d}) == ["d", "c"]


def test_trivial_risk_difference_defers_to_travel_time():
    # 1 mile of Severe (inside the 5 mi bucket) should not beat a much faster route.
    tiny = route([L.SEVERE] + [L.LOW] * 99, duration=3000)
    clean = route([L.LOW] * 100, duration=6000)
    assert rank({"tiny": tiny, "clean": clean})[0] == "tiny"


def test_explain_mentions_severe_gap():
    best = route([L.LOW] * 10, duration=4000)
    other = route([L.SEVERE] * 5 + [L.LOW] * 5, duration=3000)
    text = " ".join(explain("b", {"a": other, "b": best}, {"a": "Route A", "b": "Route B"}))
    assert "Severe" in text
    assert "Adds" in text
