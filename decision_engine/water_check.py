from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from decision_engine.engine import DecisionEngine, DecisionResult, ZoneState

@dataclass
class WaterRequirementResult:
    zone_id: str
    is_required: bool
    urgency: str                    # NONE | LOW | MEDIUM | HIGH | CRITICAL
    recommended_duration_minutes: int
    confidence: float
    guard_triggered: Optional[str]
    reason: str
    evaluated_at: str

    def to_dict(self) -> dict:
        return {
            "zone_id": self.zone_id,
            "is_required": self.is_required,
            "urgency": self.urgency,
            "recommended_duration_minutes": self.recommended_duration_minutes,
            "confidence": round(self.confidence, 4),
            "guard_triggered": self.guard_triggered,
            "reason": self.reason,
            "evaluated_at": self.evaluated_at,
        }

def _classify_urgency(
    moisture: float,
    threshold: float,
    confidence: float,
    is_required: bool,
) -> str:
    if not is_required:
        return "NONE"
    deficit_ratio = (threshold - moisture) / max(threshold, 0.01)
    if deficit_ratio > 0.6 or moisture < 0.12:
        return "CRITICAL"
    if deficit_ratio > 0.45 or confidence > 0.85:
        return "HIGH"
    if deficit_ratio > 0.25 or confidence > 0.70:
        return "MEDIUM"
    return "LOW"


def is_water_required(
    zone_state: ZoneState,
    engine: Optional[DecisionEngine] = None,
) -> WaterRequirementResult:
    engine = engine or DecisionEngine()
    decision: DecisionResult = engine.decide(zone_state)

    urgency = _classify_urgency(
        moisture=zone_state.moisture,
        threshold=zone_state.moisture_threshold,
        confidence=decision.confidence,
        is_required=decision.irrigation_needed,
    )

    return WaterRequirementResult(
        zone_id=zone_state.zone_id,
        is_required=decision.irrigation_needed,
        urgency=urgency,
        recommended_duration_minutes=decision.recommended_duration_minutes,
        confidence=decision.confidence,
        guard_triggered=decision.guard_triggered,
        reason=decision.reason,
        evaluated_at=datetime.now(tz=timezone.utc).isoformat(),
    )
