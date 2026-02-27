import pytest
import time
from decision_engine.engine import DecisionEngine, ZoneState, DecisionResult
from decision_engine.water_check import is_water_required


def make_zone(**kwargs) -> ZoneState:
    defaults = dict(
        zone_id="zone-1",
        moisture=0.20,
        temperature_c=28.0,
        humidity_pct=60.0,
        wind_speed_mps=2.0,
        rain_probability=0.0,
        moisture_threshold=0.30,
        crop_type_enc=6,
        soil_type_enc=2,
    )
    defaults.update(kwargs)
    return ZoneState(**defaults)


def test_rain_suppression():
    engine = DecisionEngine()
    zone = make_zone(rain_probability=0.85)
    result = engine.decide(zone)
    assert not result.irrigation_needed
    assert result.guard_triggered == "RAIN_SUPPRESSION"


def test_low_moisture_threshold_override():
    engine = DecisionEngine()
    # Very dry — threshold override should trigger
    zone = make_zone(moisture=0.10, moisture_threshold=0.30)
    result = engine.decide(zone)
    assert result.irrigation_needed
    assert "THRESHOLD_OVERRIDE_LOW" in (result.guard_triggered or "")


def test_high_moisture_no_irrigation():
    engine = DecisionEngine()
    zone = make_zone(moisture=0.50, moisture_threshold=0.30)
    result = engine.decide(zone)
    assert not result.irrigation_needed
    assert "THRESHOLD_OVERRIDE_HIGH" in (result.guard_triggered or "")


def test_cooldown_prevents_repeat():
    engine = DecisionEngine()
    engine.record_irrigation("zone-1")
    zone = make_zone(moisture=0.15)
    result = engine.decide(zone)
    assert result.guard_triggered == "COOLDOWN"


def test_decision_result_has_all_fields():
    engine = DecisionEngine()
    zone = make_zone()
    result = engine.decide(zone)
    assert isinstance(result, DecisionResult)
    assert result.zone_id == "zone-1"
    assert isinstance(result.irrigation_needed, bool)
    assert 0 <= result.confidence <= 1


def test_is_water_required_returns_structured():
    zone = make_zone(moisture=0.50, rain_probability=0.0)
    result = is_water_required(zone)
    assert result.zone_id == "zone-1"
    assert result.urgency in ("NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert isinstance(result.is_required, bool)
