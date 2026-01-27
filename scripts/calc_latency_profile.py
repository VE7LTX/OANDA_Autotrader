import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from oanda_autotrader.trade_latency_gate import (
    TradeLatencyGateConfig,
    profile_path,
    suggest_thresholds,
    write_profile,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="live")
    parser.add_argument("--instrument", default="USD_CAD")
    parser.add_argument("--source", choices=["stream", "monitor"], default="stream")
    parser.add_argument("--input")
    parser.add_argument("--since-seconds", type=int, default=120)
    parser.add_argument("--min-pos-samples", type=int, default=20)
    parser.add_argument("--legacy-ok", action="store_true")
    return parser.parse_args()


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = int(round(pct * (len(values) - 1)))
    return values[max(0, min(index, len(values) - 1))]


def main() -> None:
    args = parse_args()
    now = datetime.now(tz=timezone.utc)
    cutoff = now.timestamp() - args.since_seconds
    if args.input:
        input_path = args.input
    else:
        input_path = "data/stream_latency.jsonl" if args.source == "stream" else "data/monitor.jsonl"
    raw_values: list[float] = []
    with open(input_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if args.source == "monitor":
                ts_str = payload.get("ts")
                if not ts_str:
                    continue
                try:
                    ts_val = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    continue
                if ts_val < cutoff:
                    continue
                trade_gate = payload.get("trade_gate") or {}
                if trade_gate.get("mode") != args.mode:
                    continue
                if trade_gate.get("instrument") != args.instrument:
                    continue
                raw = trade_gate.get("last_raw_ms")
                if raw is None:
                    continue
                raw_values.append(raw)
            else:
                ts_str = payload.get("ts")
                ts_val: float | None = None
                if ts_str:
                    try:
                        ts_val = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                    except ValueError:
                        ts_val = None
                if ts_val is None:
                    received_ts = payload.get("received_ts")
                    if received_ts is None:
                        continue
                    ts_val = float(received_ts)
                if ts_val < cutoff:
                    continue
                mode = payload.get("mode")
                instrument = payload.get("instrument")
                if mode is None or instrument is None:
                    if not args.legacy_ok:
                        continue
                    mode = args.mode
                    instrument = args.instrument
                if mode != args.mode:
                    continue
                if instrument != args.instrument:
                    continue
                raw = payload.get("latency_ms_raw")
                if raw is None:
                    continue
                raw_values.append(raw)

    cfg = TradeLatencyGateConfig(mode=args.mode, instrument=args.instrument)
    pos_raw = [value for value in raw_values if value >= 0]
    neg_raw = [value for value in raw_values if value < 0]
    backlog_count = sum(1 for value in raw_values if value > 2000)
    outlier_count = sum(
        1 for value in raw_values if value > cfg.outlier_high_ms or value < -cfg.skew_outlier_ms
    )
    top_5_pos_raw = sorted(pos_raw, reverse=True)[:5]
    max_pos_raw = max(pos_raw) if pos_raw else None
    skew_rate = (len(neg_raw) / len(raw_values)) if raw_values else 0.0
    if len(pos_raw) >= args.min_pos_samples:
        warn, block = suggest_thresholds(
            pos_raw,
            warn_min=cfg.warn_ms_min,
            warn_max=cfg.warn_ms_max,
            block_min=cfg.block_ms_min,
            block_max=cfg.block_ms_max,
        )
    else:
        warn, block = cfg.warn_ms_min, cfg.block_ms_min
    cfg.backlog_warn_ms = warn
    cfg.backlog_block_ms = block
    cfg.clamp()

    out = {
        "ts": now.isoformat(),
        "mode": args.mode,
        "instrument": args.instrument,
        "sample_count": len(raw_values),
        "total_raw": len(raw_values),
        "neg_raw": len(neg_raw),
        "pos_raw": len(pos_raw),
        "skew_rate": skew_rate,
        "backlog_count": backlog_count,
        "outlier_count": outlier_count,
        "max_pos_raw": max_pos_raw,
        "top_5_pos_raw": top_5_pos_raw,
        "p50_ms": _percentile(pos_raw, 0.50),
        "p95_ms": _percentile(pos_raw, 0.95),
        "p99_ms": _percentile(pos_raw, 0.99),
        "min_pos_samples": args.min_pos_samples,
        "suggested_warn_ms": cfg.backlog_warn_ms,
        "suggested_block_ms": cfg.backlog_block_ms,
    }
    path = profile_path(args.mode, args.instrument)
    write_profile(path, out)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
