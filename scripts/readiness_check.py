import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import scripts.pipeline_status as pipeline_status


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--warn-seconds", type=float, default=120.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    parsed = pipeline_status.parse_args()
    parsed.json = True
    parsed.warn_seconds = args.warn_seconds

    # Reuse pipeline_status output by invoking the module directly.
    # We'll emulate by running main() and capturing exit code isn't necessary here.
    # Instead, call pipeline_status main by reconstructing outputs.
    now = pipeline_status._now_ts()
    monitor_path = parsed.monitor_path
    pred_path = parsed.pred_path
    scores_path = parsed.scores_path

    monitor_exists = os.path.exists(monitor_path)
    monitor_mtime = os.path.getmtime(monitor_path) if monitor_exists else None
    monitor_age = pipeline_status._age_seconds(monitor_mtime, now)

    pred_exists = os.path.exists(pred_path)
    pred_line = pipeline_status._last_json_line(pred_path) if pred_exists else None
    pred_ts = pipeline_status._parse_iso(pred_line.get("ts")) if pred_line else None
    pred_age = pipeline_status._age_seconds(pred_ts, now)

    scores_exists = os.path.exists(scores_path)
    score_line = pipeline_status._last_json_line(scores_path) if scores_exists else None
    score_ts = None
    if score_line:
        score_ts = pipeline_status._parse_iso(score_line.get("scored_ts") or score_line.get("ts"))
    score_age = pipeline_status._age_seconds(score_ts, now)

    candles_dir = Path(parsed.candles_dir)
    candle_files = sorted(
        [p for p in candles_dir.glob(f"{parsed.candles_pattern}*.jsonl")],
        key=lambda p: p.stat().st_mtime,
    )
    candle_file = candle_files[-1] if candle_files else None
    candle_line = pipeline_status._last_json_line(str(candle_file)) if candle_file else None
    candle_ts = pipeline_status._parse_iso(candle_line.get("time")) if candle_line else None
    candle_age = pipeline_status._age_seconds(candle_ts, now)

    warn_limit = args.warn_seconds
    monitor_limit = warn_limit if warn_limit is not None else parsed.fresh_monitor_s
    pred_limit = warn_limit if warn_limit is not None else parsed.fresh_pred_s
    score_limit = warn_limit if warn_limit is not None else parsed.fresh_score_s
    candle_limit = warn_limit if warn_limit is not None else parsed.fresh_candle_s

    def reason_and_hint(exists: bool, age: float | None, limit: float, missing_hint: str, stale_hint: str):
        if not exists:
            return "missing", missing_hint
        if age is None:
            return "missing", missing_hint
        if age > limit:
            return "stale", stale_hint
        return "ok", None

    monitor_reason, monitor_hint = reason_and_hint(
        monitor_exists,
        monitor_age,
        monitor_limit,
        "monitor loop not running",
        "monitor loop not running",
    )
    pred_reason, pred_hint = reason_and_hint(
        pred_exists,
        pred_age,
        pred_limit,
        "prediction file missing",
        "prediction job not running / stuck",
    )
    score_reason, score_hint = reason_and_hint(
        scores_exists,
        score_age,
        score_limit,
        "scores file missing",
        "scoring job not running / waiting on horizon",
    )
    candle_reason, candle_hint = reason_and_hint(
        candle_file is not None,
        candle_age,
        candle_limit,
        "candle file not found, capture likely not started",
        "run scripts/launch_capture.ps1 (or capture script)",
    )

    payload = {
        "ready": False,
        "monitor": {
            "age_s": monitor_age,
            "fresh": monitor_age is not None and monitor_age <= monitor_limit,
            "reason": monitor_reason,
            "hint": monitor_hint,
        },
        "predictions": {
            "age_s": pred_age,
            "fresh": pred_age is not None and pred_age <= pred_limit,
            "reason": pred_reason,
            "hint": pred_hint,
        },
        "scores": {
            "age_s": score_age,
            "fresh": score_age is not None and score_age <= score_limit,
            "reason": score_reason,
            "hint": score_hint,
        },
        "candles": {
            "age_s": candle_age,
            "fresh": candle_age is not None and candle_age <= candle_limit,
            "reason": candle_reason,
            "hint": candle_hint,
        },
    }
    payload["ready"] = all(item.get("fresh") for item in payload.values() if isinstance(item, dict))

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        status_label = "READY" if payload["ready"] else "NOT_READY"
        print(status_label)
        for name, info in payload.items():
            if name == "ready":
                continue
            line = f"{name:<12} {'OK' if info['fresh'] else 'STALE':<6} age={info['age_s'] if info['age_s'] is not None else '--'}"
            if info.get("hint"):
                line += f"  hint={info['hint']}"
            print(line)
    raise SystemExit(0 if payload["ready"] else 2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(1)
