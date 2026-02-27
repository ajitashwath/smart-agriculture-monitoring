from __future__ import annotations

import random
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd

from ml_engine.evaporation import compute_evaporation_rate

CROP_ENCODING = {
    "wheat": 0, "rice": 1, "maize": 2, "cotton": 3,
    "sugarcane": 4, "vegetables": 5, "tomato": 6, "potato": 7,
}
SOIL_ENCODING = {
    "clay": 0, "sandy": 1, "loamy": 2,
    "silty": 3, "peaty": 4, "chalky": 5,
}

CROP_PARAMS = {
    "wheat":      (0.30, 0.10, 5.0),
    "rice":       (0.40, 0.20, 8.0),
    "maize":      (0.33, 0.12, 6.0),
    "cotton":     (0.32, 0.11, 5.5),
    "sugarcane":  (0.38, 0.16, 7.5),
    "vegetables": (0.31, 0.11, 5.5),
    "tomato":     (0.35, 0.12, 5.5),
    "potato":     (0.32, 0.12, 5.0),
}

FEATURE_COLS = [
    "soil_moisture", "temperature_c", "humidity_pct",
    "wind_speed_mps", "rain_probability", "et0_mm_day",
    "crop_type_enc", "soil_type_enc",
]


def _label_irrigation(
    moisture: float,
    rain_prob: float,
    et0: float,
    field_capacity: float,
    wilting_point: float,
    crop_req: float,
) -> Tuple[bool, int]:
    if rain_prob >= 0.70:
        return False, 0
    available = field_capacity - wilting_point
    stress = (field_capacity - moisture) / (available + 1e-9)
    if stress < 0.45:
        return False, 0
    deficit_mm = max(0.0, crop_req - (moisture * 1000 * available * 0.3))
    duration = max(5, min(60, int(15 * stress + deficit_mm * 2 + et0 * 0.8)))
    return True, duration


def generate_dataset(
    n_samples: int = 5000,
    output_path: str = "ml_engine/data/sams_training.csv",
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    crops = list(CROP_PARAMS.keys())
    soils = list(SOIL_ENCODING.keys())

    records = []
    for _ in range(n_samples):
        crop = random.choice(crops)
        soil = random.choice(soils)
        fc, wp, req = CROP_PARAMS[crop]

        moisture = float(rng.uniform(wp - 0.02, fc + 0.05))
        moisture = np.clip(moisture, 0.05, 0.55)
        temp_c = float(rng.normal(28.0, 5.0))
        humidity = float(rng.uniform(30.0, 95.0))
        wind = float(rng.exponential(2.0))
        rain_prob = float(rng.choice([0.0, 0.2, 0.5, 0.8, 1.0],
                                      p=[0.35, 0.25, 0.20, 0.12, 0.08]))

        et_result = compute_evaporation_rate(temp_c, humidity, wind)
        et0 = et_result.et0_mm_day

        irrigate, duration = _label_irrigation(moisture, rain_prob, et0, fc, wp, req)

        records.append({
            "soil_moisture": round(moisture, 4),
            "temperature_c": round(temp_c, 2),
            "humidity_pct": round(humidity, 2),
            "wind_speed_mps": round(wind, 2),
            "rain_probability": rain_prob,
            "et0_mm_day": round(et0, 3),
            "crop_type_enc": CROP_ENCODING[crop],
            "soil_type_enc": SOIL_ENCODING[soil],
            "irrigation_needed": int(irrigate),
            "recommended_duration_min": duration,
        })

    df = pd.DataFrame(records)
    df.to_csv(output_path, index=False)
    print(f"[DataGen] Generated {n_samples} samples → {output_path}")
    print(f"          Irrigation rate: {df['irrigation_needed'].mean():.1%}")
    return df


if __name__ == "__main__":
    generate_dataset()
