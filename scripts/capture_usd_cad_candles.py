"""
Capture USD_CAD candles to JSONL for model training.
"""

from __future__ import annotations

import json
import sys
import time

sys.path.insert(0, "src")

from oanda_autotrader.app import load_instruments_client


def main():
    client = load_instruments_client("accounts.yaml", "live", "Primary")
    payload = client.get_candles(
        "USD_CAD",
        price="M",
        granularity="S5",
        count=500,
    )
    candles = payload.get("candles", [])
    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    path = f"data/usd_cad_candles_{ts}.jsonl"

    if candles:
        import os

        os.makedirs("data", exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            for candle in candles:
                handle.write(json.dumps(candle) + "\n")

    print(f"wrote {len(candles)} candles to {path}")


if __name__ == "__main__":
    main()
