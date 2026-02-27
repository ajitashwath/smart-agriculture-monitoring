from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import classification_report, mean_absolute_error
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from ml_engine.dataset_generator import generate_dataset

FEATURE_COLS = [
    "soil_moisture", "temperature_c", "humidity_pct",
    "wind_speed_mps", "rain_probability", "et0_mm_day",
    "crop_type_enc", "soil_type_enc",
]
MODEL_DIR = Path(__file__).parent / "models"


def train(n_samples: int = 5000, seed: int = 42) -> dict:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    df = generate_dataset(n_samples=n_samples, seed=seed)
    X = df[FEATURE_COLS].values.astype(np.float32)
    y_cls = df["irrigation_needed"].values
    y_reg = df["recommended_duration_min"].values.astype(np.float32)

    X_train, X_test, y_cls_tr, y_cls_te, y_reg_tr, y_reg_te = train_test_split(
        X, y_cls, y_reg, test_size=0.2, random_state=seed, stratify=y_cls
    )

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    clf = RandomForestClassifier(
        n_estimators=150,
        max_depth=12,
        min_samples_leaf=3,
        class_weight="balanced",
        random_state=seed,
        n_jobs=-1,
    )
    clf.fit(X_train_s, y_cls_tr)
    cls_preds = clf.predict(X_test_s)
    cls_report = classification_report(y_cls_te, cls_preds, output_dict=True)

    reg = RandomForestRegressor(
        n_estimators=100,
        max_depth=10,
        random_state=seed,
        n_jobs=-1,
    )
    mask = y_cls_tr == 1
    if mask.sum() > 10:
        reg.fit(X_train_s[mask], y_reg_tr[mask])
    else:
        reg.fit(X_train_s, y_reg_tr)

    reg_preds = reg.predict(X_test_s[y_cls_te == 1])
    mae = mean_absolute_error(y_reg_te[y_cls_te == 1], reg_preds) if len(reg_preds) > 0 else 0.0

    bundle = {"clf": clf, "reg": reg, "scaler": scaler, "feature_cols": FEATURE_COLS}
    joblib.dump(bundle, MODEL_DIR / "rf_model.joblib")

    metrics = {
        "accuracy": cls_report["accuracy"],
        "precision": cls_report["1"]["precision"],
        "recall": cls_report["1"]["recall"],
        "f1": cls_report["1"]["f1-score"],
        "duration_mae_minutes": round(mae, 2),
    }
    (MODEL_DIR / "rf_metrics.json").write_text(json.dumps(metrics, indent=2))

    print(f"[RF] Accuracy={metrics['accuracy']:.3f}  "
          f"F1={metrics['f1']:.3f}  "
          f"Duration MAE={metrics['duration_mae_minutes']} min")
    print(f"[RF] Saved → {MODEL_DIR / 'rf_model.joblib'}")
    return metrics


if __name__ == "__main__":
    train()
