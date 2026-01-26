"""
Continuous autoencoder + predictor training loop.
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
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyTorch is required. Install with: pip install torch") from exc


FEATURE_NAMES = [
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


def iter_feature_rows(path: str) -> Iterable[dict]:
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def load_matrix(path: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows = []
    closes = []
    returns = []
    for row in iter_feature_rows(path):
        values = [row.get(name) for name in FEATURE_NAMES]
        if any(v is None for v in values):
            continue
        rows.append(values)
        closes.append(row.get("close"))
        returns.append(row.get("log_return"))
    matrix = np.array(rows, dtype=np.float32)
    return matrix, np.array(closes, dtype=np.float32), np.array(returns, dtype=np.float32)


class AutoEncoderPredictor(nn.Module):
    def __init__(self, input_dim: int, bottleneck: int) -> None:
        super().__init__()
        hidden = max(8, input_dim // 2)
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, bottleneck),
            nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(bottleneck, hidden),
            nn.ReLU(),
            nn.Linear(hidden, input_dim),
        )
        self.predictor = nn.Sequential(
            nn.Linear(bottleneck, max(4, bottleneck)),
            nn.ReLU(),
            nn.Linear(max(4, bottleneck), 1),
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        z = self.encoder(x)
        recon = self.decoder(z)
        pred = self.predictor(z).squeeze(-1)
        return recon, pred


def write_jsonl(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", default="data/usd_cad_features.jsonl")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--bottleneck", type=int, default=8)
    parser.add_argument("--use-cuda", action="store_true")
    parser.add_argument("--status-path", default="data/ae_status.jsonl")
    parser.add_argument("--pred-path", default="data/predictions.jsonl")
    parser.add_argument("--val-split", type=float, default=0.2)
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--retrain-interval", type=int, default=60)
    args = parser.parse_args()

    device = torch.device("cuda" if args.use_cuda and torch.cuda.is_available() else "cpu")

    while True:
        matrix, closes, returns = load_matrix(args.features)
        if matrix.size == 0 or len(returns) < 2:
            time.sleep(args.retrain_interval)
            continue

        # Align X_t -> y_{t+1}
        X = matrix[:-1]
        y = returns[1:]

        # Normalize per-feature
        mean = X.mean(axis=0)
        std = X.std(axis=0)
        std[std == 0] = 1.0
        Xn = (X - mean) / std

        n = Xn.shape[0]
        split = int(n * (1 - args.val_split))
        X_train, X_val = Xn[:split], Xn[split:]
        y_train, y_val = y[:split], y[split:]

        model = AutoEncoderPredictor(Xn.shape[1], args.bottleneck).to(device)
        optim = torch.optim.Adam(model.parameters(), lr=args.lr)
        loss_fn = nn.MSELoss()

        X_train_t = torch.tensor(X_train, device=device)
        y_train_t = torch.tensor(y_train, device=device)
        X_val_t = torch.tensor(X_val, device=device)
        y_val_t = torch.tensor(y_val, device=device)

        steps = max(1, len(X_train_t) // args.batch_size)
        for epoch in range(1, args.epochs + 1):
            model.train()
            perm = torch.randperm(len(X_train_t), device=device)
            epoch_loss = 0.0
            pred_loss_total = 0.0
            for i in range(steps):
                idx = perm[i * args.batch_size : (i + 1) * args.batch_size]
                xb = X_train_t[idx]
                yb = y_train_t[idx]
                recon, pred = model(xb)
                recon_loss = loss_fn(recon, xb)
                pred_loss = loss_fn(pred, yb)
                loss = recon_loss + pred_loss
                optim.zero_grad()
                loss.backward()
                optim.step()
                epoch_loss += loss.item()
                pred_loss_total += pred_loss.item()

            # Validation
            model.eval()
            with torch.no_grad():
                recon_v, pred_v = model(X_val_t)
                val_loss = loss_fn(recon_v, X_val_t).item() + loss_fn(pred_v, y_val_t).item()
                pred_err = (pred_v - y_val_t).cpu().numpy()
                pred_std = float(pred_err.std()) if pred_err.size else 0.0

            status = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "epoch": epoch,
                "loss": round(epoch_loss / steps, 6),
                "val_loss": round(val_loss, 6),
                "pred_loss": round(pred_loss_total / steps, 6),
                "pred_std": round(pred_std, 6),
                "device": str(device),
            }
            write_jsonl(args.status_path, status)

        # Forecast using last feature row
        last_x = (matrix[-1] - mean) / std
        last_close = float(closes[-1])
        model.eval()
        with torch.no_grad():
            _, pred = model(torch.tensor(last_x, device=device).unsqueeze(0))
            pred_return = float(pred.item())

        horizon = []
        for i in range(1, args.horizon + 1):
            mean_close = last_close * ((1 + pred_return) ** i)
            band = pred_std * i * last_close
            horizon.append(
                {
                    "step": i,
                    "mean": mean_close,
                    "low": mean_close - band,
                    "high": mean_close + band,
                }
            )

        write_jsonl(
            args.pred_path,
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "base_close": last_close,
                "horizon": horizon,
            },
        )

        time.sleep(args.retrain_interval)


if __name__ == "__main__":
    main()
