import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from oanda_autotrader.app import build_stream_client
from oanda_autotrader.config import load_account_groups, resolve_account_credentials, select_account
from oanda_autotrader.stream_metrics import StreamMetrics


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="live")
    parser.add_argument("--account", default="Primary")
    parser.add_argument("--instrument", default="USD_CAD")
    parser.add_argument("--seconds", type=int, default=1800)
    parser.add_argument("--output", default="data/stream_latency.jsonl")
    parser.add_argument("--log-interval", type=float, default=1.0)
    parser.add_argument("--pid-file", default=None)
    return parser.parse_args()


async def run_capture(args) -> None:
    groups = load_account_groups("accounts.yaml")
    group_name = args.mode
    if group_name == "practice":
        group_name = "demo"
    group_obj, entry = select_account(groups, group_name, args.account)
    config = resolve_account_credentials(group_obj, entry)

    metrics = StreamMetrics(window_seconds=10)
    end_ts = time.time() + args.seconds
    last_log_ts: float | None = None

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    async with build_stream_client(config) as stream:
        async for msg in stream.stream_pricing(entry.account_id, [args.instrument]):
            payload = msg.raw if hasattr(msg, "raw") else msg
            if payload.get("type") != "PRICE":
                continue
            ts = time.time()
            metrics.record_latency(payload.get("time"), ts)
            if last_log_ts is None or ts - last_log_ts >= args.log_interval:
                last_log_ts = ts
                sample = {
                    "ts": datetime.now(tz=timezone.utc).isoformat(),
                    "mode": args.mode,
                    "instrument": args.instrument,
                    "received_ts": ts,
                    "server_time": payload.get("time"),
                    "latency_ms_raw": metrics.last_latency_raw_ms,
                    "latency_ms_clamped": metrics.last_latency_ms,
                    "skew_ms": metrics.last_skew_ms,
                    "is_backlog": metrics.last_backlog,
                }
                with open(args.output, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(sample) + "\n")
            if ts >= end_ts:
                break


def main() -> None:
    args = parse_args()
    if args.pid_file:
        os.makedirs(os.path.dirname(args.pid_file), exist_ok=True)
        with open(args.pid_file, "w", encoding="ascii") as handle:
            handle.write(str(os.getpid()))
    asyncio.run(run_capture(args))


if __name__ == "__main__":
    main()
