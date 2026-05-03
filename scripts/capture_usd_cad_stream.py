"""
Continuous USD_CAD capture (stream + periodic candles) for model training.
"""

from __future__ import annotations

import asyncio
import json
import os
import time

from oanda_autotrader.app import build_instruments_client, build_stream_client
from oanda_autotrader.config import load_account_groups, resolve_account_credentials, select_account
from oanda_autotrader.logging_config import setup_logging


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value else default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def _now_bucket(minutes: int) -> str:
    return time.strftime("%Y%m%d_%H%M", time.gmtime(time.time() // (minutes * 60) * (minutes * 60)))


def _open_rotating_file(base_dir: str, prefix: str, minutes: int):
    os.makedirs(base_dir, exist_ok=True)
    bucket = _now_bucket(minutes)
    path = os.path.join(base_dir, f"{prefix}_{bucket}.jsonl")
    return bucket, path, open(path, "a", encoding="utf-8")


async def stream_pricing(
    config,
    *,
    instrument: str,
    out_dir: str,
    rotate_minutes: int,
):
    bucket = None
    handle = None

    def on_event(event: dict):
        event["received_ts"] = time.time()
        if handle:
            handle.write(json.dumps(event) + "\n")
            handle.flush()

    async with build_stream_client(config, on_event=on_event) as stream:
        async for msg in stream.stream_pricing(config.account_id, [instrument]):
            new_bucket = _now_bucket(rotate_minutes)
            if bucket != new_bucket:
                if handle:
                    handle.close()
                bucket, _, handle = _open_rotating_file(out_dir, "usd_cad_stream", rotate_minutes)
            payload = msg.raw if hasattr(msg, "raw") else msg
            payload["received_ts"] = time.time()
            handle.write(json.dumps(payload) + "\n")
            handle.flush()


async def poll_candles(
    config,
    *,
    out_dir: str,
    instrument: str,
    granularity: str,
    price: str,
    count: int,
    interval_seconds: int,
):
    client = build_instruments_client(config)
    os.makedirs(out_dir, exist_ok=True)
    while True:
        payload = client.get_candles(
            instrument,
            price=price,
            granularity=granularity,
            count=count,
        )
        ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        path = os.path.join(out_dir, f"usd_cad_candles_{ts}.jsonl")
        with open(path, "w", encoding="utf-8") as handle:
            for candle in payload.get("candles", []):
                handle.write(json.dumps(candle) + "\n")
        await asyncio.sleep(interval_seconds)


async def main():
    setup_logging(json_output=True)

    group = _env("OANDA_CAPTURE_GROUP", "live")
    account = _env("OANDA_CAPTURE_ACCOUNT", "Primary")
    instrument = _env("OANDA_CAPTURE_INSTRUMENT", "USD_CAD")
    out_dir = _env("OANDA_CAPTURE_DIR", "data")
    rotate_minutes = _env_int("OANDA_CAPTURE_ROTATE_MINUTES", 60)

    candle_interval = _env_int("OANDA_CAPTURE_CANDLE_INTERVAL_SECONDS", 300)
    candle_granularity = _env("OANDA_CAPTURE_GRANULARITY", "S5")
    candle_price = _env("OANDA_CAPTURE_PRICE", "M")
    candle_count = _env_int("OANDA_CAPTURE_COUNT", 500)

    groups = load_account_groups("accounts.yaml")
    group_obj, entry = select_account(groups, group, account)
    config = resolve_account_credentials(group_obj, entry)

    await asyncio.gather(
        stream_pricing(
            config,
            instrument=instrument,
            out_dir=out_dir,
            rotate_minutes=rotate_minutes,
        ),
        poll_candles(
            config,
            out_dir=out_dir,
            instrument=instrument,
            granularity=candle_granularity,
            price=candle_price,
            count=candle_count,
            interval_seconds=candle_interval,
        ),
    )


if __name__ == "__main__":
    asyncio.run(main())
