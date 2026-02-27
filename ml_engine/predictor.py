from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import numpy as np

MODEL_DIR = Path(__file__).parent / "models"
MODEL_TYPE = os.getenv("ML_MODEL_TYPE", "rf")
CONFIDENCE_THRESHOLD = float(os.getenv("ML_CONFIDENCE_THRESHOLD", "0.65"))

FEATURE_ORDER = [
    "soil_moisture", "temperature_c", "humidity_pct",
    "wind_speed_mps", "rain_probability", "et0_mm_day",
    "crop_type_enc", "soil_type_enc",
]


@dataclass
class PredictionResult:
    irrigation_needed: bool
    confidence: float
    recommended_duration_minutes: int
    model_type: str

    def to_dict(self) -> dict:
        return {
            "irrigation_needed": self.irrigation_needed,
            "confidence": round(self.confidence, 4),
            "recommended_duration_minutes": self.recommended_duration_minutes,
            "model_type": self.model_type,
        }


class IrrigationPredictor:
    def __init__(self, model_type: Optional[str] = None) -> None:
        self._model_type = (model_type or MODEL_TYPE).lower()
        self._clf = None
        self._reg = None
        self._scaler = None
        self._torch_model = None
        self._torch_scaler_mean = None
        self._torch_scaler_scale = None
        self._loaded = False

    def _load_rf(self) -> None:
        import joblib
        path = MODEL_DIR / "rf_model.joblib"
        if not path.exists():
            raise FileNotFoundError(f"RF model not found: {path}. Run train_rf.py first.")
        bundle = joblib.load(path)
        self._clf = bundle["clf"]
        self._reg = bundle["reg"]
        self._scaler = bundle["scaler"]

    def _load_torch(self) -> None:
        import torch
        from ml_engine.train_torch import IrrigationNet

        path = MODEL_DIR / "torch_model.pt"
        if not path.exists():
            raise FileNotFoundError(f"Torch model not found: {path}. Run train_torch.py first.")

        bundle = torch.load(path, map_location="cpu", weights_only=False)
        input_dim = bundle.get("input_dim", 8)
        model = IrrigationNet(input_dim=input_dim)
        model.load_state_dict(bundle["model_state"])
        model.eval()
        self._torch_model = model
        self._torch_scaler_mean = np.array(bundle["scaler_mean"])
        self._torch_scaler_scale = np.array(bundle["scaler_scale"])

    def load(self) -> "IrrigationPredictor":
        if self._loaded:
            return self
        if self._model_type == "rf":
            self._load_rf()
        elif self._model_type == "torch":
            self._load_torch()
        else:
            raise ValueError(f"Unknown model type: {self._model_type}")
        self._loaded = True
        return self

    def _extract_features(self, features: Dict[str, float]) -> np.ndarray:
        return np.array([features.get(k, 0.0) for k in FEATURE_ORDER], dtype=np.float32)

    def predict(self, features: Dict[str, float]) -> PredictionResult:
        if not self._loaded:
            self.load()

        x = self._extract_features(features).reshape(1, -1)

        if self._model_type == "rf":
            x_scaled = self._scaler.transform(x)
            proba = self._clf.predict_proba(x_scaled)[0]
            confidence = float(proba[1])
            needed = confidence >= CONFIDENCE_THRESHOLD
            duration = 0
            if needed:
                duration = max(5, int(self._reg.predict(x_scaled)[0]))

        elif self._model_type == "torch":
            import torch
            x_scaled = (x - self._torch_scaler_mean) / (self._torch_scaler_scale + 1e-8)
            x_t = torch.tensor(x_scaled, dtype=torch.float32)
            with torch.no_grad():
                logit, dur_out = self._torch_model(x_t)
            confidence = float(torch.sigmoid(logit).item())
            needed = confidence >= CONFIDENCE_THRESHOLD
            duration = max(5, int(dur_out.item() * 60)) if needed else 0
        else:
            raise ValueError(f"Unknown model type: {self._model_type}")

        return PredictionResult(
            irrigation_needed=needed,
            confidence=confidence,
            recommended_duration_minutes=max(0, min(duration, 120)),
            model_type=self._model_type,
        )


_predictor: Optional[IrrigationPredictor] = None


def get_predictor() -> IrrigationPredictor:
    global _predictor
    if _predictor is None:
        _predictor = IrrigationPredictor()
        _predictor.load()
    return _predictor
