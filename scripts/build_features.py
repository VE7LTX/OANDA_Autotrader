"""
Build feature rows (RSI/SMA/EMA/returns/volume) from candle JSONL files.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from typing import Iterable


def iter_candles(paths: list[str]) -> Iterable[dict]:
    for path in paths:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)


def _close_volume(candle: dict) -> tuple[float | None, int | None, str | None]:
    mid = candle.get("mid") or {}
    close = mid.get("c")
    volume = candle.get("volume") or candle.get("v")
    time_val = candle.get("time")
    return (float(close) if close is not None else None, volume, time_val)


def sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def ema(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    k = 2 / (window + 1)
    ema_val = values[-window]
    for v in values[-window + 1 :]:
        ema_val = v * k + ema_val * (1 - k)
    return ema_val


def rsi(values: list[float], window: int) -> float | None:
    if len(values) < window + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(-window, 0):
        delta = values[i] - values[i - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100 - (100 / (1 + rs))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="data")
    parser.add_argument("--pattern", default="usd_cad_candles_")
    parser.add_argument("--output", default="data/usd_cad_features.jsonl")
    parser.add_argument("--rsi", type=int, default=14)
    parser.add_argument("--sma-fast", type=int, default=10)
    parser.add_argument("--sma-slow", type=int, default=20)
    parser.add_argument("--ema-fast", type=int, default=10)
    parser.add_argument("--ema-slow", type=int, default=20)
    args = parser.parse_args()

    paths = sorted(
        os.path.join(args.input_dir, name)
        for name in os.listdir(args.input_dir)
        if name.startswith(args.pattern) and name.endswith(".jsonl")
    )
    closes: list[float] = []
    rows = []
    for candle in iter_candles(paths):
        close, volume, time_val = _close_volume(candle)
        if close is None:
            continue
        closes.append(close)
        sma_fast = sma(closes, args.sma_fast)
        sma_slow = sma(closes, args.sma_slow)
        ema_fast = ema(closes, args.ema_fast)
        ema_slow = ema(closes, args.ema_slow)
        rsi_val = rsi(closes, args.rsi)
        ret = None
        log_ret = None
        if len(closes) > 1:
            ret = (closes[-1] - closes[-2]) / closes[-2]
            log_ret = math.log(closes[-1] / closes[-2])

        if None in (sma_fast, sma_slow, ema_fast, ema_slow, rsi_val, ret, log_ret):
            continue
        rows.append(
            {
                "time": time_val,
                "close": close,
                "volume": volume,
                "return": ret,
                "log_return": log_ret,
                "sma_fast": sma_fast,
                "sma_slow": sma_slow,
                "ema_fast": ema_fast,
                "ema_slow": ema_slow,
                "rsi": rsi_val,
            }
        )

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    print(f"wrote {len(rows)} feature rows to {args.output}")


if __name__ == "__main__":
    main()
