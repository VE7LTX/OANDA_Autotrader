from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from oanda_autotrader.retrain_gate import evaluate_retrain_gate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scores-path", default="data/prediction_scores.jsonl")
    parser.add_argument("--monitor-path", default="data/monitor.jsonl")
    parser.add_argument("--pred-path", default="data/predictions_latest.jsonl")
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    decision = evaluate_retrain_gate(
        scores_path=args.scores_path,
        monitor_path=args.monitor_path,
        predictions_path=args.pred_path,
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
    payload = {
        "allow": decision.allow,
        "reason": decision.reason,
        "coverage": decision.coverage,
        "mae": decision.mae,
        "mae_threshold": decision.mae_threshold,
        "window_n": decision.window_n,
        "fields_used": decision.fields_used,
        "blocked": decision.blocked,
        "stale": decision.stale,
        "details": decision.details,
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
