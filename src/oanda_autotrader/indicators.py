"""
Lightweight indicator helpers for deterministic strategy scoring.
"""

from __future__ import annotations


def extract_closes(candles: list[dict]) -> list[float]:
    return [float((c.get("mid") or {}).get("c")) for c in candles if (c.get("mid") or {}).get("c") is not None]


def extract_highs(candles: list[dict]) -> list[float]:
    return [float((c.get("mid") or {}).get("h")) for c in candles if (c.get("mid") or {}).get("h") is not None]


def extract_lows(candles: list[dict]) -> list[float]:
    return [float((c.get("mid") or {}).get("l")) for c in candles if (c.get("mid") or {}).get("l") is not None]


def average(values: list[float]) -> float:
    return sum(values) / len(values)


def ema(values: list[float], period: int) -> float:
    if len(values) < period:
        raise ValueError("Not enough values for EMA.")
    multiplier = 2.0 / (period + 1)
    current = average(values[:period])
    for value in values[period:]:
        current = (value - current) * multiplier + current
    return current


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        raise ValueError("Not enough values for RSI.")
    gains = 0.0
    losses = 0.0
    for idx in range(-period, 0):
        delta = values[idx] - values[idx - 1]
        if delta >= 0:
            gains += delta
        else:
            losses += abs(delta)
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - (100.0 / (1.0 + rs))


def atr(candles: list[dict], period: int = 14) -> float:
    highs = extract_highs(candles)
    lows = extract_lows(candles)
    closes = extract_closes(candles)
    if len(highs) <= period or len(lows) <= period or len(closes) <= period:
        raise ValueError("Not enough candles for ATR.")
    true_ranges: list[float] = []
    for idx in range(1, len(candles)):
        high = highs[idx]
        low = lows[idx]
        prev_close = closes[idx - 1]
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return average(true_ranges[-period:])
