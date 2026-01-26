"""
Score predictions against realized candles and write labeled records.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
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
            rows.append(json.loads(line))
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


def main() -> None:
    pred_path = "data/predictions.jsonl"
    score_path = "data/prediction_scores.jsonl"
    candle_dir = "data"
    candle_files = [
        os.path.join(candle_dir, name)
        for name in os.listdir(candle_dir)
        if name.startswith("usd_cad_candles_") and name.endswith(".jsonl")
    ]
    candle_map = load_candles(sorted(candle_files))

    preds = load_predictions(pred_path)
    existing = load_scores(score_path)
    scored_ts = {row.get("ts") for row in existing}

    with open(score_path, "a", encoding="utf-8") as handle:
        for pred in preds:
            ts = pred.get("ts")
            if not ts or ts in scored_ts:
                continue
            horizon = pred.get("horizon") or []
            results = []
            hits = 0
            errors = []
            base_ts = pred.get("ts")
            base_dt = None
            if base_ts:
                try:
                    base_dt = datetime.fromisoformat(base_ts.replace("Z", "+00:00"))
                except ValueError:
                    base_dt = None
            interval_secs = pred.get("interval_secs", 5)
            for item in horizon:
                step = item.get("step")
                mean = item.get("mean")
                low = item.get("low")
                high = item.get("high")
                # Candle times are expected to be aligned by 5s; approximate by step index.
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
                results.append(
                    {
                        "step": step,
                        "actual": actual,
                        "hit": hit,
                    }
                )

            coverage = hits / max(len(horizon), 1)
            mae = sum(errors) / max(len(errors), 1) if errors else None
            out = {
                "ts": ts,
                "coverage": coverage,
                "mae": mae,
                "results": results,
                "scored_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            handle.write(json.dumps(out) + "\n")


if __name__ == "__main__":
    main()
