from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from land_setup.schemas import FarmProfile, SoilType


SOIL_MOISTURE_OFFSETS: Dict[SoilType, float] = {
    SoilType.CLAY: 0.05,
    SoilType.SANDY: -0.04,
    SoilType.LOAMY: 0.0,
    SoilType.SILTY: 0.02,
    SoilType.PEATY: 0.08,
    SoilType.CHALKY: -0.02,
}


def _slope_runoff_factor(slope_degrees: float) -> float:
    if slope_degrees <= 2:
        return 1.0
    elif slope_degrees <= 10:
        return 0.95
    elif slope_degrees <= 20:
        return 0.88
    else:
        return 0.80


@dataclass
class CalibrationResult:
    farm_id: str
    soil_moisture_offset: float
    slope_runoff_factor: float
    effective_field_capacity: float
    effective_wilting_point: float
    recommended_thresholds: Dict[str, float]

    def to_dict(self) -> dict:
        return {
            "farm_id": self.farm_id,
            "soil_moisture_offset": round(self.soil_moisture_offset, 4),
            "slope_runoff_factor": round(self.slope_runoff_factor, 4),
            "effective_field_capacity": round(self.effective_field_capacity, 4),
            "effective_wilting_point": round(self.effective_wilting_point, 4),
            "recommended_thresholds": {
                k: round(v, 4) for k, v in self.recommended_thresholds.items()
            },
        }


def calibrate_farm(profile: FarmProfile) -> CalibrationResult:
    soil_offset = SOIL_MOISTURE_OFFSETS.get(profile.soil.soil_type, 0.0)
    slope_factor = _slope_runoff_factor(profile.topology.slope_degrees)

    raw_fc = profile.soil.field_capacity
    raw_wp = profile.soil.wilting_point

    eff_fc = min(raw_fc * slope_factor + soil_offset, 0.55)
    eff_wp = max(raw_wp + soil_offset * 0.5, 0.05)

    plant_available = eff_fc - eff_wp
    trigger = eff_wp + (plant_available * 0.50)

    recommended: Dict[str, float] = {
        node.node_id: round(trigger, 3) for node in profile.nodes
    }

    return CalibrationResult(
        farm_id=profile.farm_id,
        soil_moisture_offset=soil_offset,
        slope_runoff_factor=slope_factor,
        effective_field_capacity=eff_fc,
        effective_wilting_point=eff_wp,
        recommended_thresholds=recommended,
    )
