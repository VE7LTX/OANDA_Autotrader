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
    parser.add_argument("--warn-seconds", type=float, default=120.0)
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

    monitor_exists = os.path.exists(monitor_path)
    monitor_mtime = os.path.getmtime(monitor_path) if monitor_exists else None
    monitor_age = _age_seconds(monitor_mtime, now)

    pred_exists = os.path.exists(pred_path)
    pred_line = _last_json_line(pred_path) if pred_exists else None
    pred_ts = _parse_iso(pred_line.get("ts")) if pred_line else None
    pred_age = _age_seconds(pred_ts, now)

    scores_exists = os.path.exists(scores_path)
    score_line = _last_json_line(scores_path) if scores_exists else None
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

    warn_limit = args.warn_seconds
    monitor_limit = warn_limit if warn_limit is not None else args.fresh_monitor_s
    pred_limit = warn_limit if warn_limit is not None else args.fresh_pred_s
    score_limit = warn_limit if warn_limit is not None else args.fresh_score_s
    candle_limit = warn_limit if warn_limit is not None else args.fresh_candle_s

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
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "monitor": {
            "path": monitor_path,
            "exists": monitor_exists,
            "age_s": monitor_age,
            "fresh": _fresh(monitor_age, monitor_limit),
            "status": "OK" if _fresh(monitor_age, monitor_limit) else "STALE",
            "reason": monitor_reason,
            "hint": monitor_hint,
        },
        "predictions": {
            "path": pred_path,
            "exists": pred_exists,
            "ts": pred_line.get("ts") if pred_line else None,
            "age_s": pred_age,
            "fresh": _fresh(pred_age, pred_limit),
            "status": "OK" if _fresh(pred_age, pred_limit) else "STALE",
            "reason": pred_reason,
            "hint": pred_hint,
        },
        "scores": {
            "path": scores_path,
            "exists": scores_exists,
            "ts": score_line.get("scored_ts") if score_line else None,
            "age_s": score_age,
            "fresh": _fresh(score_age, score_limit),
            "status": "OK" if _fresh(score_age, score_limit) else "STALE",
            "reason": score_reason,
            "hint": score_hint,
        },
        "candles": {
            "file": str(candle_file) if candle_file else None,
            "ts": candle_line.get("time") if candle_line else None,
            "age_s": candle_age,
            "fresh": _fresh(candle_age, candle_limit),
            "status": "OK" if _fresh(candle_age, candle_limit) else "STALE",
            "reason": candle_reason,
            "hint": candle_hint,
        },
    }

    overall_ok = all(
        item.get("fresh") for item in payload.values() if isinstance(item, dict)
    )

    if args.json:
        print(json.dumps(payload, indent=2))
        raise SystemExit(0 if overall_ok else 2)

    def line(label: str, info: dict) -> str:
        status = "OK" if info.get("fresh") else "STALE"
        age = info.get("age_s")
        age_label = f"{age:.1f}s" if age is not None else "--"
        hint = info.get("hint")
        hint_text = f"  hint={hint}" if hint else ""
        return f"{label:<12} {status:<6} age={age_label}{hint_text}"

    print(line("monitor", payload["monitor"]))
    print(line("predictions", payload["predictions"]))
    print(line("scores", payload["scores"]))
    print(line("candles", payload["candles"]))

    raise SystemExit(0 if overall_ok else 2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(1)
