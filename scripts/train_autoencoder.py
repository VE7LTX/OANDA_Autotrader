"""
Train a simple autoencoder on feature windows and write status updates.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Iterable

import numpy as np

try:
    import torch
    from torch import nn
except ImportError as exc:  # pragma: no cover - runtime dependency
    raise SystemExit(
        "PyTorch is required for training. Install with: pip install torch"
    ) from exc


def iter_feature_rows(path: str) -> Iterable[dict]:
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def build_matrix(path: str, features: list[str]) -> np.ndarray:
    rows = []
    for row in iter_feature_rows(path):
        values = [row.get(name) for name in features]
        if any(v is None for v in values):
            continue
        rows.append(values)
    return np.array(rows, dtype=np.float32)


class AutoEncoder(nn.Module):
    def __init__(self, input_dim: int, bottleneck: int) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, max(8, input_dim // 2)),
            nn.ReLU(),
            nn.Linear(max(8, input_dim // 2), bottleneck),
            nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(bottleneck, max(8, input_dim // 2)),
            nn.ReLU(),
            nn.Linear(max(8, input_dim // 2), input_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.encoder(x)
        return self.decoder(z)


def write_status(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", default="data/usd_cad_features.jsonl")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--bottleneck", type=int, default=8)
    parser.add_argument("--use-cuda", action="store_true")
    parser.add_argument("--status-path", default="data/ae_status.jsonl")
    args = parser.parse_args()

    feature_names = [
        "close",
        "volume",
        "vwap",
        "return",
        "log_return",
        "sma_fast",
        "sma_slow",
        "ema_fast",
        "ema_slow",
        "rsi",
        "macd",
        "macd_signal",
        "macd_hist",
        "bb_mid",
        "bb_upper",
        "bb_lower",
        "bb_width",
        "atr",
        "plus_di",
        "minus_di",
        "adx",
        "stoch_k",
        "stoch_d",
        "obv",
    ]

    data = build_matrix(args.features, feature_names)
    if data.size == 0:
        raise SystemExit("No feature rows found. Run build_features.py first.")

    # Normalize per-feature.
    mean = data.mean(axis=0)
    std = data.std(axis=0)
    std[std == 0] = 1.0
    data = (data - mean) / std

    device = torch.device("cuda" if args.use_cuda and torch.cuda.is_available() else "cpu")
    model = AutoEncoder(data.shape[1], args.bottleneck).to(device)
    optim = torch.optim.Adam(model.parameters(), lr=args.lr)
    loss_fn = nn.MSELoss()

    tensor = torch.tensor(data, device=device)
    n = tensor.shape[0]
    steps = max(1, n // args.batch_size)

    for epoch in range(1, args.epochs + 1):
        model.train()
        perm = torch.randperm(n, device=device)
        epoch_loss = 0.0
        for i in range(steps):
            idx = perm[i * args.batch_size : (i + 1) * args.batch_size]
            batch = tensor[idx]
            recon = model(batch)
            loss = loss_fn(recon, batch)
            optim.zero_grad()
            loss.backward()
            optim.step()
            epoch_loss += loss.item()
        epoch_loss /= steps

        status = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "epoch": epoch,
            "loss": round(epoch_loss, 6),
            "device": str(device),
        }
        write_status(args.status_path, status)
        print(status)


if __name__ == "__main__":
    main()
