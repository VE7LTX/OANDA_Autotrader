import argparse
import json
import time
from datetime import datetime, timezone

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
    parser.add_argument("--input", default="data/stream_latency.jsonl")
    parser.add_argument("--since-seconds", type=int, default=120)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    now = time.time()
    cutoff = now - args.since_seconds
    raw_values = []
    with open(args.input, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            received_ts = payload.get("received_ts")
            if received_ts is None or received_ts < cutoff:
                continue
            raw = payload.get("latency_ms_raw")
            if raw is None:
                continue
            raw_values.append(raw)

    cfg = TradeLatencyGateConfig(mode=args.mode, instrument=args.instrument)
    warn, block = suggest_thresholds(
        raw_values,
        warn_min=cfg.warn_ms_min,
        warn_max=cfg.warn_ms_max,
        block_min=cfg.block_ms_min,
        block_max=cfg.block_ms_max,
    )
    cfg.backlog_warn_ms = warn
    cfg.backlog_block_ms = block
    cfg.clamp()

    out = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "mode": args.mode,
        "instrument": args.instrument,
        "sample_count": len(raw_values),
        "suggested_warn_ms": cfg.backlog_warn_ms,
        "suggested_block_ms": cfg.backlog_block_ms,
    }
    path = profile_path(args.mode, args.instrument)
    write_profile(path, out)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
