import pytest

from trips.domain.risk import RiskLevel as L
from trips.domain.risk import assess, rain_level, snow_level, wind_level


@pytest.mark.parametrize(
    "mph,expected",
    [(0, L.LOW), (24.9, L.LOW), (25, L.MODERATE), (34.9, L.MODERATE), (35, L.HIGH), (44.9, L.HIGH), (45, L.SEVERE), (54.9, L.SEVERE), (55, L.NO_TRAVEL), (90, L.NO_TRAVEL)],
)
def test_wind_bands(mph, expected):
    assert wind_level(mph) == expected


@pytest.mark.parametrize(
    "v,expected",
    [(0, L.LOW), (0.09, L.LOW), (0.10, L.MODERATE), (0.25, L.MODERATE), (0.26, L.HIGH), (0.50, L.HIGH), (0.51, L.SEVERE), (1.00, L.SEVERE), (1.01, L.NO_TRAVEL)],
)
def test_rain_bands(v, expected):
    assert rain_level(v) == expected


@pytest.mark.parametrize(
    "v,expected",
    [(0, L.LOW), (0.49, L.LOW), (0.5, L.MODERATE), (1.0, L.MODERATE), (1.1, L.HIGH), (2.0, L.HIGH), (2.5, L.SEVERE), (3.0, L.SEVERE), (3.01, L.NO_TRAVEL)],
)
def test_snow_bands(v, expected):
    assert snow_level(v) == expected


def test_overall_is_worst_factor():
    a = assess(wind_mph=10, rain_in_hr=0.3, snow_in_hr=2.5, load_lb=10_000)
    assert a.level == L.SEVERE and a.snow == L.SEVERE and a.rain == L.HIGH


def test_wind_55_is_no_travel_for_any_load():
    assert assess(55, 0, 0, 0).level == L.NO_TRAVEL


def test_heavy_load_with_severe_wind_is_no_travel():
    assert assess(50, 0, 0, 30_001).level == L.NO_TRAVEL
    assert assess(50, 0, 0, 30_000).level == L.SEVERE  # not strictly greater
    assert assess(50, 0, 0, 30_001).load_adjusted


def test_heavy_load_with_high_wind_is_severe():
    a = assess(40, 0, 0, 40_001)
    assert a.level == L.SEVERE and a.load_adjusted
    assert assess(40, 0, 0, 40_000).level == L.HIGH


def test_load_rule_never_lowers_risk():
    # Snow already No Travel; a high-wind load rule must not downgrade it.
    assert assess(40, 0, 4.0, 45_000).level == L.NO_TRAVEL


def test_calm_weather_has_no_drivers():
    a = assess(5, 0, 0, 79_000)
    assert a.level == L.LOW and a.drivers == ()
