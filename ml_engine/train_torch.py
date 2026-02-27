from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

from ml_engine.dataset_generator import FEATURE_COLS, generate_dataset

MODEL_DIR = Path(__file__).parent / "models"


class IrrigationNet(nn.Module):
    def __init__(self, input_dim: int = 8) -> None:
        super().__init__()
        self.shared = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.LayerNorm(64),
            nn.GELU(),
            nn.Dropout(0.2),
            nn.Linear(64, 32),
            nn.LayerNorm(32),
            nn.GELU(),
        )
        self.cls_head = nn.Sequential(nn.Linear(32, 1))
        self.reg_head = nn.Sequential(
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
        )

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        shared = self.shared(x)
        cls_logit = self.cls_head(shared).squeeze(-1)
        duration = self.reg_head(shared).squeeze(-1)
        return cls_logit, duration


def train(n_samples: int = 5000, epochs: int = 40, seed: int = 42) -> dict:
    torch.manual_seed(seed)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    device = torch.device("cpu")

    df = generate_dataset(n_samples=n_samples, seed=seed)
    X = df[FEATURE_COLS].values.astype(np.float32)
    y_cls = df["irrigation_needed"].values.astype(np.float32)
    y_reg = df["recommended_duration_min"].values.astype(np.float32)

    X_tr, X_te, y_cls_tr, y_cls_te, y_reg_tr, y_reg_te = train_test_split(
        X, y_cls, y_reg, test_size=0.2, random_state=seed
    )

    scaler = StandardScaler()
    X_tr = scaler.fit_transform(X_tr).astype(np.float32)
    X_te = scaler.transform(X_te).astype(np.float32)

    train_ds = TensorDataset(
        torch.tensor(X_tr), torch.tensor(y_cls_tr), torch.tensor(y_reg_tr)
    )
    train_dl = DataLoader(train_ds, batch_size=64, shuffle=True)

    model = IrrigationNet(input_dim=X_tr.shape[1]).to(device)
    optimizer = optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    pos_ratio = y_cls_tr.sum() / max(1, len(y_cls_tr) - y_cls_tr.sum())
    pos_weight = torch.tensor([1.0 / max(0.1, pos_ratio)], device=device)
    bce_loss = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    mse_loss = nn.MSELoss()

    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        for xb, yb_cls, yb_reg in train_dl:
            xb, yb_cls, yb_reg = xb.to(device), yb_cls.to(device), yb_reg.to(device)
            optimizer.zero_grad()
            logit, duration = model(xb)
            loss_cls = bce_loss(logit, yb_cls)
            mask = yb_cls > 0.5
            loss_reg = mse_loss(duration[mask], yb_reg[mask] / 60.0) if mask.sum() > 0 else torch.tensor(0.0)
            loss = loss_cls + 0.3 * loss_reg
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item()
        scheduler.step()
        if epoch % 10 == 0:
            print(f"[Torch] Epoch {epoch:3d}/{epochs}  loss={total_loss/len(train_dl):.4f}")

    model.eval()
    with torch.no_grad():
        X_te_t = torch.tensor(X_te)
        logits, _ = model(X_te_t)
        preds = (torch.sigmoid(logits) > 0.5).numpy().astype(int)
        acc = (preds == y_cls_te.astype(int)).mean()

    metrics = {"accuracy": round(float(acc), 4), "epochs": epochs}
    (MODEL_DIR / "torch_metrics.json").write_text(json.dumps(metrics, indent=2))

    bundle = {
        "model_state": model.state_dict(),
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "feature_cols": FEATURE_COLS,
        "input_dim": X_tr.shape[1],
    }
    torch.save(bundle, MODEL_DIR / "torch_model.pt")
    print(f"[Torch] Accuracy={acc:.3f}")
    print(f"[Torch] Saved → {MODEL_DIR / 'torch_model.pt'}")
    return metrics


if __name__ == "__main__":
    train()
