import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--monitor-path", default="data/monitor.jsonl")
    parser.add_argument("--pred-path", default="data/predictions_latest.jsonl")
    parser.add_argument("--scores-path", default="data/prediction_scores.jsonl")
    parser.add_argument("--candles-dir", default="data")
    parser.add_argument("--candles-pattern", default="usd_cad_candles_")
    parser.add_argument("--fresh-monitor-s", type=float, default=45.0)
    parser.add_argument("--fresh-pred-s", type=float, default=120.0)
    parser.add_argument("--fresh-score-s", type=float, default=300.0)
    parser.add_argument("--fresh-candle-s", type=float, default=120.0)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _now_ts() -> float:
    return time.time()


def _parse_iso(ts: str | None) -> float | None:
    if not ts:
        return None
    raw = ts.strip()
    if raw.endswith("Z"):
        raw = raw[:-1]
    if "." in raw:
        head, frac = raw.split(".", 1)
        frac = frac[:6].ljust(6, "0")
        raw = f"{head}.{frac}"
    try:
        dt = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _last_json_line(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        if size == 0:
            return None
        chunk = min(size, 65536)
        handle.seek(-chunk, os.SEEK_END)
        data = handle.read().decode("utf-8", errors="ignore")
    lines = [line for line in data.splitlines() if line.strip()]
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return None


def _age_seconds(ts: float | None, now: float) -> float | None:
    if ts is None:
        return None
    return max(0.0, now - ts)


def _fresh(age: float | None, limit: float) -> bool:
    return age is not None and age <= limit


def main() -> None:
    args = parse_args()
    now = _now_ts()

    monitor_path = args.monitor_path
    pred_path = args.pred_path
    scores_path = args.scores_path

    monitor_mtime = os.path.getmtime(monitor_path) if os.path.exists(monitor_path) else None
    monitor_age = _age_seconds(monitor_mtime, now)

    pred_line = _last_json_line(pred_path)
    pred_ts = _parse_iso(pred_line.get("ts")) if pred_line else None
    pred_age = _age_seconds(pred_ts, now)

    score_line = _last_json_line(scores_path)
    score_ts = None
    if score_line:
        score_ts = _parse_iso(score_line.get("scored_ts") or score_line.get("ts"))
    score_age = _age_seconds(score_ts, now)

    candles_dir = Path(args.candles_dir)
    candle_files = sorted(
        [p for p in candles_dir.glob(f"{args.candles_pattern}*.jsonl")],
        key=lambda p: p.stat().st_mtime,
    )
    candle_file = candle_files[-1] if candle_files else None
    candle_line = _last_json_line(str(candle_file)) if candle_file else None
    candle_ts = _parse_iso(candle_line.get("time")) if candle_line else None
    candle_age = _age_seconds(candle_ts, now)

    payload = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "monitor": {
            "path": monitor_path,
            "exists": os.path.exists(monitor_path),
            "age_s": monitor_age,
            "fresh": _fresh(monitor_age, args.fresh_monitor_s),
        },
        "predictions": {
            "path": pred_path,
            "exists": os.path.exists(pred_path),
            "ts": pred_line.get("ts") if pred_line else None,
            "age_s": pred_age,
            "fresh": _fresh(pred_age, args.fresh_pred_s),
        },
        "scores": {
            "path": scores_path,
            "exists": os.path.exists(scores_path),
            "ts": score_line.get("scored_ts") if score_line else None,
            "age_s": score_age,
            "fresh": _fresh(score_age, args.fresh_score_s),
        },
        "candles": {
            "file": str(candle_file) if candle_file else None,
            "ts": candle_line.get("time") if candle_line else None,
            "age_s": candle_age,
            "fresh": _fresh(candle_age, args.fresh_candle_s),
        },
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return

    def line(label: str, info: dict) -> str:
        status = "OK" if info.get("fresh") else "STALE"
        age = info.get("age_s")
        age_label = f"{age:.1f}s" if age is not None else "--"
        return f"{label:<12} {status:<6} age={age_label}"

    print(line("monitor", payload["monitor"]))
    print(line("predictions", payload["predictions"]))
    print(line("scores", payload["scores"]))
    print(line("candles", payload["candles"]))


if __name__ == "__main__":
    main()
