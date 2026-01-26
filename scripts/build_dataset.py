"""
Build training windows from USD_CAD candle JSONL files.

Outputs:
- CSV or JSONL windows with normalized features per window.
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


def load_close_prices(candles: Iterable[dict]) -> list[float]:
    prices = []
    for candle in candles:
        mid = candle.get("mid") or {}
        close = mid.get("c")
        if close is None:
            continue
        prices.append(float(close))
    return prices


def window_series(values: list[float], window: int, stride: int) -> list[list[float]]:
    windows = []
    i = 0
    while i + window <= len(values):
        windows.append(values[i : i + window])
        i += stride
    return windows


def normalize_window(values: list[float]) -> list[float]:
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(variance) if variance > 0 else 1.0
    return [(v - mean) / std for v in values]


def write_jsonl(windows: list[list[float]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for window in windows:
            handle.write(json.dumps({"window": window}) + "\n")


def write_csv(windows: list[list[float]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for window in windows:
            handle.write(",".join(f"{v:.8f}" for v in window) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="data")
    parser.add_argument("--pattern", default="usd_cad_candles_")
    parser.add_argument("--window", type=int, default=64)
    parser.add_argument("--stride", type=int, default=8)
    parser.add_argument("--output", default="data/usd_cad_windows.jsonl")
    parser.add_argument("--format", choices=["jsonl", "csv"], default="jsonl")
    args = parser.parse_args()

    paths = sorted(
        os.path.join(args.input_dir, name)
        for name in os.listdir(args.input_dir)
        if name.startswith(args.pattern) and name.endswith(".jsonl")
    )
    candles = iter_candles(paths)
    closes = load_close_prices(candles)
    windows = window_series(closes, args.window, args.stride)
    windows = [normalize_window(w) for w in windows]

    if args.format == "csv":
        write_csv(windows, args.output)
    else:
        write_jsonl(windows, args.output)

    print(f"wrote {len(windows)} windows to {args.output}")


if __name__ == "__main__":
    main()
