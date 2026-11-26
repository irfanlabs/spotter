import pytest

from trips.domain import geo


def test_polyline_roundtrip():
    path = [(41.8781, -87.6298), (39.7392, -104.9903), (34.0522, -118.2437)]
    out = geo.decode_polyline(geo.encode_polyline(path, 6), 6)
    for got, want in zip(out, path):
        assert got == pytest.approx(want, abs=1e-6)
    assert len(out) == len(path)


def test_truncated_polyline_raises():
    with pytest.raises(ValueError):
        geo.decode_polyline("_", 6)


def test_haversine_chicago_dallas():
    assert geo.haversine_mi((41.8781, -87.6298), (32.7767, -96.797)) == pytest.approx(802, abs=5)


def test_point_at_clamps_and_interpolates():
    path = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
    cum = geo.cumulative_miles(path)
    assert geo.point_at(path, cum, -5)[0] == (0.0, 0.0)
    assert geo.point_at(path, cum, 1e9)[0] == (0.0, 2.0)
    mid, _ = geo.point_at(path, cum, cum[-1] / 2)
    assert mid[1] == pytest.approx(1.0, abs=1e-6)


def test_simplify_keeps_endpoints_and_corners():
    path = [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2)]
    out = geo.simplify(path, 0.01)
    assert out == [(0, 0), (0, 2), (2, 2)]


def test_path_similarity_identical_and_distinct():
    a = [(40.0, -100.0), (40.0, -90.0)]
    b = [(44.0, -100.0), (44.0, -90.0)]
    assert geo.path_similarity(a, a) == 1.0
    assert geo.path_similarity(a, b) == 0.0
