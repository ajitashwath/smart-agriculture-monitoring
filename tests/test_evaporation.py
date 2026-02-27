import pytest
from ml_engine.evaporation import compute_evaporation_rate, EvaporationResult


def test_returns_evaporation_result():
    result = compute_evaporation_rate(28.0, 60.0, 2.5)
    assert isinstance(result, EvaporationResult)


def test_et0_positive():
    result = compute_evaporation_rate(28.0, 60.0, 2.5)
    assert result.et0_mm_day > 0


def test_high_humidity_lower_vpd():
    r_low = compute_evaporation_rate(28.0, 40.0, 2.0)
    r_high = compute_evaporation_rate(28.0, 90.0, 2.0)
    assert r_high.vapor_pressure_deficit < r_low.vapor_pressure_deficit


def test_wind_increases_penman():
    r_calm = compute_evaporation_rate(28.0, 60.0, 0.5)
    r_windy = compute_evaporation_rate(28.0, 60.0, 8.0)
    assert r_windy.penman_mm_day > r_calm.penman_mm_day


def test_with_min_max_temps():
    result = compute_evaporation_rate(28.0, 60.0, 2.5, temp_min_c=20.0, temp_max_c=36.0)
    assert result.et0_mm_day > 0


def test_extreme_humidity_clamped():
    result = compute_evaporation_rate(28.0, 100.0, 1.0)
    assert result.vapor_pressure_deficit >= 0
    assert result.et0_mm_day >= 0
