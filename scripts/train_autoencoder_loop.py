"""
Continuous autoencoder + predictor training loop.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from typing import Iterable

import numpy as np
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from oanda_autotrader.retrain_gate import evaluate_retrain_gate

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
    def __init__(self, input_dim: int, bottleneck: int, horizon: int) -> None:
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
            nn.Linear(max(4, bottleneck), horizon),
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        z = self.encoder(x)
        recon = self.decoder(z)
        pred = self.predictor(z)
        return recon, pred


def write_jsonl(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def write_json_latest(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
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
    parser.add_argument("--pred-path", default=None)
    parser.add_argument("--pred-latest-path", default="data/predictions_latest.jsonl")
    parser.add_argument("--pred-archive-dir", default="data/predictions")
    parser.add_argument("--archive-predictions", action="store_true")
    parser.add_argument("--recon-path", default="data/recon.jsonl")
    parser.add_argument("--val-split", type=float, default=0.2)
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--retrain-interval", type=int, default=60)
    parser.add_argument("--k", type=float, default=1.5)
    parser.add_argument("--interval-secs", type=int, default=5)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-delta", type=float, default=0.0005)
    parser.add_argument("--scores-path", default="data/prediction_scores.jsonl")
    parser.add_argument("--monitor-path", default="data/monitor.jsonl")
    parser.add_argument("--candles-dir", default="data")
    parser.add_argument("--candles-pattern", default="usd_cad_candles_")
    parser.add_argument("--gate-window", type=int, default=50)
    parser.add_argument("--min-coverage", type=float, default=0.60)
    parser.add_argument("--mae-threshold", type=float, default=0.00010)
    parser.add_argument("--mae-vol-scale", type=float, default=0.25)
    parser.add_argument("--stale-monitor-s", type=float, default=45.0)
    parser.add_argument("--stale-pred-s", type=float, default=120.0)
    parser.add_argument("--stale-score-s", type=float, default=300.0)
    parser.add_argument("--stale-candle-s", type=float, default=120.0)
    parser.add_argument("--force-retrain", action="store_true")
    args = parser.parse_args()
    pred_latest_path = args.pred_latest_path or args.pred_path or "data/predictions_latest.jsonl"

    device = torch.device("cuda" if args.use_cuda and torch.cuda.is_available() else "cpu")

    while True:
        matrix, closes, returns = load_matrix(args.features)
        if matrix.size == 0 or len(closes) < (args.horizon + 1):
            time.sleep(args.retrain_interval)
            continue

        if not args.force_retrain:
            gate = evaluate_retrain_gate(
                scores_path=args.scores_path,
                monitor_path=args.monitor_path,
                predictions_path=pred_latest_path,
                candles_dir=args.candles_dir,
                candles_pattern=args.candles_pattern,
                window_n=args.gate_window,
                min_coverage=args.min_coverage,
                fixed_mae_threshold=args.mae_threshold,
                volatility_scale=args.mae_vol_scale,
                stale_monitor_s=args.stale_monitor_s,
                stale_pred_s=args.stale_pred_s,
                stale_score_s=args.stale_score_s,
                stale_candle_s=args.stale_candle_s,
            )
            coverage = f"{gate.coverage:.3f}" if gate.coverage is not None else "na"
            mae = f"{gate.mae:.6f}" if gate.mae is not None else "na"
            mae_thr = f"{gate.mae_threshold:.6f}" if gate.mae_threshold is not None else "na"
            decision = "ALLOW" if gate.allow else "SKIP"
            print(
                "retrain_gate",
                f"window_n={gate.window_n}",
                f"coverage={coverage}",
                f"mae={mae}",
                f"mae_threshold={mae_thr}",
                f"decision={decision}",
                f"reason={gate.reason}",
            )
            if not gate.allow:
                if args.once:
                    break
                time.sleep(args.retrain_interval)
                continue
        else:
            print("retrain_gate", "force=true", "decision=ALLOW", "reason=forced")

        # Align X_t -> delta close for each horizon step.
        n = len(closes) - args.horizon
        X = matrix[:n]
        y = np.stack(
            [
                [
                    closes[i + k] - closes[i + k - 1]
                    for k in range(1, args.horizon + 1)
                ]
                for i in range(n)
            ],
            axis=0,
        )
        y = np.clip(y, -args.max_delta, args.max_delta)

        # Normalize per-feature
        mean = X.mean(axis=0)
        std = X.std(axis=0)
        std[std == 0] = 1.0
        Xn = (X - mean) / std

        # Normalize target deltas per horizon step
        y_mean = y.mean(axis=0)
        y_std = y.std(axis=0)
        y_std[y_std == 0] = 1.0
        y_norm = (y - y_mean) / y_std

        split = int(n * (1 - args.val_split))
        X_train, X_val = Xn[:split], Xn[split:]
        y_train, y_val = y_norm[:split], y_norm[split:]

        model = AutoEncoderPredictor(Xn.shape[1], args.bottleneck, args.horizon).to(device)
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
                pred_std_norm = pred_err.std(axis=0) if pred_err.size else np.zeros(args.horizon)
                pred_std = np.clip(pred_std_norm * y_std, 0.0, args.max_delta)

            status = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "epoch": epoch,
                "loss": round(epoch_loss / steps, 6),
                "val_loss": round(val_loss, 6),
                "pred_loss": round(pred_loss_total / steps, 6),
                "pred_std_mean": round(float(np.mean(pred_std)) if len(pred_std) else 0.0, 6),
                "device": str(device),
            }
            write_jsonl(args.status_path, status)

        # Reconstruction error stats on recent window.
        model.eval()
        with torch.no_grad():
            recon_all, _ = model(torch.tensor(Xn, device=device))
            recon_all = recon_all.cpu().numpy()
        recon_close = recon_all[:, 0] * std[0] + mean[0]
        actual_close = matrix[:n, 0]
        errors = np.abs(actual_close - recon_close[: len(actual_close)])
        window_errors = errors[-500:] if len(errors) > 500 else errors
        mean_error = float(window_errors.mean()) if window_errors.size else 0.0
        std_error = float(window_errors.std()) if window_errors.size else 0.0
        last_recon = float(recon_close[-1])
        last_actual = float(actual_close[-1])
        last_error = abs(last_actual - last_recon)
        recon_payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "actual": last_actual,
            "recon": last_recon,
            "error": last_error,
            "mean_error": mean_error,
            "std_error": std_error,
            "k": args.k,
        }
        write_jsonl(args.recon_path, recon_payload)

        # Forecast using last feature row
        last_x = (matrix[n - 1] - mean) / std
        last_close = float(closes[n - 1])
        model.eval()
        with torch.no_grad():
            _, pred = model(torch.tensor(last_x, device=device).unsqueeze(0))
            pred_deltas = pred.squeeze(0).cpu().numpy() * y_std + y_mean
            pred_deltas = np.clip(pred_deltas, -args.max_delta, args.max_delta)

        horizon = []
        cum_mu = 0.0
        cum_var = 0.0
        for i in range(1, args.horizon + 1):
            mu = float(pred_deltas[i - 1])
            sigma = float(pred_std[i - 1]) if len(pred_std) >= i else 0.0
            cum_mu += mu
            cum_var += sigma * sigma
            mean_close = last_close + cum_mu
            band = args.k * math.sqrt(cum_var)
            horizon.append(
                {
                    "step": i,
                    "mu": mu,
                    "sigma": sigma,
                    "mean": mean_close,
                    "low": mean_close - band,
                    "high": mean_close + band,
                }
            )

        pred_payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model_version": os.getenv("AE_MODEL_VERSION", "ae_v1"),
            "interval_secs": args.interval_secs,
            "horizon_secs": args.horizon * args.interval_secs,
            "base_close": last_close,
            "k": args.k,
            "pred_std": pred_std.tolist() if hasattr(pred_std, "tolist") else pred_std,
            "horizon": horizon,
        }
        write_json_latest(pred_latest_path, pred_payload)
        if args.archive_predictions:
            stamp = time.strftime("%Y%m%d_%H%M", time.gmtime())
            archive_path = os.path.join(args.pred_archive_dir, f"predictions_{stamp}.jsonl")
            write_jsonl(archive_path, pred_payload)

        if args.once:
            break
        time.sleep(args.retrain_interval)


if __name__ == "__main__":
    main()
