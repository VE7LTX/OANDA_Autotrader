"""
Score predictions against realized candles and write labeled records.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List


def load_candles(paths: List[str]) -> Dict[str, float]:
    # Map ISO time -> close price (string keys for simplicity).
    data: Dict[str, float] = {}
    for path in paths:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                candle = json.loads(line)
                ts = candle.get("time")
                close = (candle.get("mid") or {}).get("c")
                if ts and close:
                    data[ts] = float(close)
    return data


def load_predictions(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if "horizon" not in payload or "interval_secs" not in payload:
                continue
            rows.append(payload)
    return rows


def load_scores(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def score_once(
    pred_path: str, score_path: str, candle_dir: str, scored_ts: set
) -> set:
    candle_files = [
        os.path.join(candle_dir, name)
        for name in os.listdir(candle_dir)
        if name.startswith("usd_cad_candles_") and name.endswith(".jsonl")
    ]
    candle_map = load_candles(sorted(candle_files))
    preds = load_predictions(pred_path)

    with open(score_path, "a", encoding="utf-8") as handle:
        for pred in preds:
            ts = pred.get("ts")
            if not ts or ts in scored_ts:
                continue
            horizon = pred.get("horizon") or []
            results = []
            hits = 0
            errors = []
            resolved = 0
            bucket_defs = [("1-3", 1, 3), ("4-8", 4, 8), ("9-12", 9, 12)]
            bucket_hits = {label: 0 for label, _, _ in bucket_defs}
            bucket_errors = {label: [] for label, _, _ in bucket_defs}
            bucket_resolved = {label: 0 for label, _, _ in bucket_defs}
            base_dt = None
            base_ts = pred.get("ts")
            try:
                base_dt = (
                    datetime.fromisoformat(base_ts.replace("Z", "+00:00"))
                    if base_ts
                    else None
                )
            except ValueError:
                base_dt = None
            interval_secs = pred.get("interval_secs", 5)
            for item in horizon:
                step = item.get("step")
                mean = item.get("mean")
                low = item.get("low")
                high = item.get("high")
                actual_ts = None
                if base_dt and step is not None:
                    actual_dt = base_dt + timedelta(seconds=step * interval_secs)
                    actual_ts = actual_dt.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
                actual = candle_map.get(actual_ts) if actual_ts else None
                hit = None
                if actual is not None and low is not None and high is not None:
                    hit = low <= actual <= high
                    hits += 1 if hit else 0
                    errors.append(abs(actual - mean))
                    resolved += 1
                    for label, start, end in bucket_defs:
                        if step is not None and start <= step <= end:
                            bucket_hits[label] += 1 if hit else 0
                            bucket_errors[label].append(abs(actual - mean))
                            bucket_resolved[label] += 1
                results.append({"step": step, "actual": actual, "hit": hit})

            coverage = hits / resolved if resolved else None
            mae = sum(errors) / len(errors) if errors else None
            buckets = []
            for label, _, _ in bucket_defs:
                b_resolved = bucket_resolved[label]
                b_hits = bucket_hits[label]
                b_errors = bucket_errors[label]
                buckets.append(
                    {
                        "label": label,
                        "coverage": (b_hits / b_resolved) if b_resolved else None,
                        "mae": (sum(b_errors) / len(b_errors)) if b_errors else None,
                        "resolved": b_resolved,
                    }
                )
            out = {
                "ts": ts,
                "coverage": coverage,
                "mae": mae,
                "results": results,
                "buckets": buckets,
                "scored_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            handle.write(json.dumps(out) + "\n")
            scored_ts.add(ts)
    return scored_ts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pred-path", default="data/predictions_latest.jsonl")
    parser.add_argument("--score-path", default="data/prediction_scores.jsonl")
    parser.add_argument("--candle-dir", default="data")
    parser.add_argument("--every", type=int, default=10)
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()

    scored_ts = {row.get("ts") for row in load_scores(args.score_path)}
    scored_ts = score_once(args.pred_path, args.score_path, args.candle_dir, scored_ts)
    if args.watch:
        while True:
            time.sleep(args.every)
            scored_ts = score_once(
                args.pred_path, args.score_path, args.candle_dir, scored_ts
            )


if __name__ == "__main__":
    main()
