import json
import pytest
from pathlib import Path
from land_setup.schemas import FarmProfile, SoilType, CropType
from land_setup.validator import load_profile, ProfileValidationError
from land_setup.calibration import calibrate_farm

SAMPLE_PROFILE_PATH = Path(__file__).parent.parent / "land_setup" / "profiles" / "farm_001.json"


def test_load_valid_profile():
    profile = load_profile(SAMPLE_PROFILE_PATH)
    assert profile.farm_id == "farm-001"
    assert profile.soil.soil_type == SoilType.LOAMY
    assert profile.crop_type == CropType.TOMATO
    assert len(profile.nodes) == 4


def test_node_ids_unique():
    profile = load_profile(SAMPLE_PROFILE_PATH)
    ids = [n.node_id for n in profile.nodes]
    assert len(ids) == len(set(ids))


def test_wilting_below_field_capacity():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        from land_setup.schemas import SoilData
        SoilData(
            soil_type=SoilType.LOAMY, ph=7.0,
            organic_matter_pct=3.0,
            field_capacity=0.20, wilting_point=0.25  # invalid
        )


def test_calibration_output():
    profile = load_profile(SAMPLE_PROFILE_PATH)
    result = calibrate_farm(profile)
    assert result.farm_id == profile.farm_id
    assert 0 < result.effective_wilting_point < result.effective_field_capacity
    assert all(0 < v < 1 for v in result.recommended_thresholds.values())
