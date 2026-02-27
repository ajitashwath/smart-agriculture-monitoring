from __future__ import annotations

import logging
import os
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ml_engine.evaporation import compute_evaporation_rate
from ml_engine.predictor import PredictionResult, get_predictor

logger = logging.getLogger("sams.decision_engine")

RAIN_THRESHOLD = float(os.getenv("RAIN_PROBABILITY_THRESHOLD", "0.6"))
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_MINUTES", "15")) * 60
ANOMALY_ZSCORE = float(os.getenv("ANOMALY_ZSCORE_THRESHOLD", "3.0"))


@dataclass
class ZoneState:
    zone_id: str
    moisture: float
    temperature_c: float
    humidity_pct: float
    wind_speed_mps: float
    rain_probability: float
    crop_type_enc: int = 6          # tomato default
    soil_type_enc: int = 2          # loamy default
    moisture_threshold: float = 0.30

@dataclass
class DecisionResult:
    zone_id: str
    irrigation_needed: bool
    confidence: float
    recommended_duration_minutes: int
    guard_triggered: Optional[str]   
    ml_decision: Optional[PredictionResult]
    reason: str
    decided_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "zone_id": self.zone_id,
            "irrigation_needed": self.irrigation_needed,
            "confidence": round(self.confidence, 4),
            "recommended_duration_minutes": self.recommended_duration_minutes,
            "guard_triggered": self.guard_triggered,
            "reason": self.reason,
            "decided_at": self.decided_at,
            "ml_prediction": self.ml_decision.to_dict() if self.ml_decision else None,
        }


class DecisionEngine:
    def __init__(self) -> None:
        self._last_irrigated: Dict[str, float] = {}
        self._moisture_history: Dict[str, List[float]] = {}
        self._history_size = 20

    def update_moisture_history(self, zone_id: str, moisture: float) -> None:
        h = self._moisture_history.setdefault(zone_id, [])
        h.append(moisture)
        if len(h) > self._history_size:
            h.pop(0)

    def is_anomaly(self, zone_id: str, moisture: float) -> bool:
        h = self._moisture_history.get(zone_id, [])
        if len(h) < 5:
            return False
        mean = statistics.mean(h)
        stdev = statistics.stdev(h) or 1e-9
        z = abs(moisture - mean) / stdev
        return z > ANOMALY_ZSCORE

    def check_cooldown(self, zone_id: str) -> bool:
        last = self._last_irrigated.get(zone_id, 0.0)
        return (time.monotonic() - last) < COOLDOWN_SECONDS

    def record_irrigation(self, zone_id: str) -> None:
        self._last_irrigated[zone_id] = time.monotonic()

    def decide(self, zone: ZoneState) -> DecisionResult:
        self.update_moisture_history(zone.zone_id, zone.moisture)
        if self.is_anomaly(zone.zone_id, zone.moisture):
            logger.warning(f"[{zone.zone_id}] Anomaly detected in moisture reading: {zone.moisture:.3f}")
            return DecisionResult(
                zone_id=zone.zone_id,
                irrigation_needed=False,
                confidence=0.0,
                recommended_duration_minutes=0,
                guard_triggered="ANOMALY",
                ml_decision=None,
                reason="Sensor anomaly detected — skipping cycle",
            )

        if zone.rain_probability >= RAIN_THRESHOLD:
            logger.info(f"[{zone.zone_id}] Rain suppression: P(rain)={zone.rain_probability:.0%}")
            return DecisionResult(
                zone_id=zone.zone_id,
                irrigation_needed=False,
                confidence=zone.rain_probability,
                recommended_duration_minutes=0,
                guard_triggered="RAIN_SUPPRESSION",
                ml_decision=None,
                reason=f"Rain forecast at {zone.rain_probability:.0%} — irrigation suppressed",
            )

        if self.check_cooldown(zone.zone_id):
            logger.info(f"[{zone.zone_id}] In cooldown window — skipping")
            return DecisionResult(
                zone_id=zone.zone_id,
                irrigation_needed=False,
                confidence=0.0,
                recommended_duration_minutes=0,
                guard_triggered="COOLDOWN",
                ml_decision=None,
                reason="Cooldown period active — next cycle pending",
            )

        if zone.moisture <= zone.moisture_threshold * 0.75:
            logger.warning(f"[{zone.zone_id}] Threshold override: moisture critically low {zone.moisture:.3f}")
            return DecisionResult(
                zone_id=zone.zone_id,
                irrigation_needed=True,
                confidence=0.95,
                recommended_duration_minutes=20,
                guard_triggered="THRESHOLD_OVERRIDE_LOW",
                ml_decision=None,
                reason=f"Critically dry ({zone.moisture:.3f}) — threshold override triggered (pre-ML)",
            )

        if zone.moisture > zone.moisture_threshold * 1.5:
            logger.info(f"[{zone.zone_id}] Moisture sufficient: {zone.moisture:.3f}")
            return DecisionResult(
                zone_id=zone.zone_id,
                irrigation_needed=False,
                confidence=0.95,
                recommended_duration_minutes=0,
                guard_triggered="THRESHOLD_OVERRIDE_HIGH",
                ml_decision=None,
                reason=f"Soil moisture ({zone.moisture:.3f}) well above threshold — no irrigation needed",
            )

        et_result = compute_evaporation_rate(
            zone.temperature_c, zone.humidity_pct, zone.wind_speed_mps
        )
        features = {
            "soil_moisture": zone.moisture,
            "temperature_c": zone.temperature_c,
            "humidity_pct": zone.humidity_pct,
            "wind_speed_mps": zone.wind_speed_mps,
            "rain_probability": zone.rain_probability,
            "et0_mm_day": et_result.et0_mm_day,
            "crop_type_enc": float(zone.crop_type_enc),
            "soil_type_enc": float(zone.soil_type_enc),
        }

        try:
            ml = get_predictor().predict(features)
        except Exception as exc:
            logger.error(f"ML prediction failed: {exc}")
            needed = zone.moisture < zone.moisture_threshold
            return DecisionResult(
                zone_id=zone.zone_id,
                irrigation_needed=needed,
                confidence=0.5,
                recommended_duration_minutes=15 if needed else 0,
                guard_triggered="ML_FAILURE_FALLBACK",
                ml_decision=None,
                reason="ML model unavailable — threshold fallback applied",
            )

        reason = (
            f"ML decision: {'irrigate' if ml.irrigation_needed else 'no action'} "
            f"(confidence={ml.confidence:.0%}, ET₀={et_result.et0_mm_day:.2f}mm/day)"
        )

        return DecisionResult(
            zone_id=zone.zone_id,
            irrigation_needed=ml.irrigation_needed,
            confidence=ml.confidence,
            recommended_duration_minutes=ml.recommended_duration_minutes,
            guard_triggered=None,
            ml_decision=ml,
            reason=reason,
        )
