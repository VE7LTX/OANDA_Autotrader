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


def _ohlcv(candle: dict) -> tuple[float | None, float | None, float | None, float | None, int | None, str | None]:
    mid = candle.get("mid") or {}
    close = mid.get("c")
    open_ = mid.get("o")
    high = mid.get("h")
    low = mid.get("l")
    volume = candle.get("volume") or candle.get("v")
    time_val = candle.get("time")
    return (
        float(open_) if open_ is not None else None,
        float(high) if high is not None else None,
        float(low) if low is not None else None,
        float(close) if close is not None else None,
        int(volume) if volume is not None else None,
        time_val,
    )


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
    highs: list[float] = []
    lows: list[float] = []
    volumes: list[int] = []
    rows = []

    macd_series: list[float] = []
    signal_series: list[float] = []
    stoch_k_series: list[float] = []

    obv = 0.0
    vwap_num = 0.0
    vwap_den = 0.0

    tr14 = None
    plus_dm14 = None
    minus_dm14 = None
    adx = None
    for candle in iter_candles(paths):
        open_, high, low, close, volume, time_val = _ohlcv(candle)
        if close is None or high is None or low is None or volume is None:
            continue
        closes.append(close)
        highs.append(high)
        lows.append(low)
        volumes.append(volume)

        # OBV
        if len(closes) > 1:
            if closes[-1] > closes[-2]:
                obv += volume
            elif closes[-1] < closes[-2]:
                obv -= volume

        # VWAP (cumulative)
        typical = (high + low + close) / 3.0
        vwap_num += typical * volume
        vwap_den += volume
        vwap = vwap_num / vwap_den if vwap_den else None
        sma_fast = sma(closes, args.sma_fast)
        sma_slow = sma(closes, args.sma_slow)
        ema_fast = ema(closes, args.ema_fast)
        ema_slow = ema(closes, args.ema_slow)
        rsi_val = rsi(closes, args.rsi)

        # MACD
        macd_val = None
        signal_val = None
        hist_val = None
        if ema_fast is not None and ema_slow is not None:
            macd_val = ema_fast - ema_slow
            macd_series.append(macd_val)
            signal_val = ema(macd_series, 9)
            if signal_val is not None:
                signal_series.append(signal_val)
                hist_val = macd_val - signal_val

        # Bollinger Bands
        bb_mid = sma(closes, 20)
        bb_upper = None
        bb_lower = None
        bb_width = None
        if len(closes) >= 20 and bb_mid is not None:
            window_vals = closes[-20:]
            mean = bb_mid
            variance = sum((v - mean) ** 2 for v in window_vals) / len(window_vals)
            std = math.sqrt(variance)
            bb_upper = mean + 2 * std
            bb_lower = mean - 2 * std
            bb_width = bb_upper - bb_lower

        # ATR + ADX (Wilder smoothing, 14)
        atr = None
        plus_di = None
        minus_di = None
        adx_val = None
        if len(closes) > 1:
            prev_close = closes[-2]
            prev_high = highs[-2]
            prev_low = lows[-2]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            plus_dm = max(high - prev_high, 0.0)
            minus_dm = max(prev_low - low, 0.0)
            if plus_dm <= minus_dm:
                plus_dm = 0.0
            if minus_dm <= plus_dm:
                minus_dm = 0.0

            if tr14 is None:
                if len(closes) >= 15:
                    tr14 = sum(
                        max(
                            highs[i] - lows[i],
                            abs(highs[i] - closes[i - 1]),
                            abs(lows[i] - closes[i - 1]),
                        )
                        for i in range(-14, 0)
                    )
                    plus_dm14 = sum(
                        max(highs[i] - highs[i - 1], 0.0) if (highs[i] - highs[i - 1]) > (lows[i - 1] - lows[i]) else 0.0
                        for i in range(-14, 0)
                    )
                    minus_dm14 = sum(
                        max(lows[i - 1] - lows[i], 0.0) if (lows[i - 1] - lows[i]) > (highs[i] - highs[i - 1]) else 0.0
                        for i in range(-14, 0)
                    )
            else:
                tr14 = tr14 - (tr14 / 14) + tr
                plus_dm14 = plus_dm14 - (plus_dm14 / 14) + plus_dm
                minus_dm14 = minus_dm14 - (minus_dm14 / 14) + minus_dm

            if tr14 and tr14 > 0:
                plus_di = 100 * (plus_dm14 / tr14)
                minus_di = 100 * (minus_dm14 / tr14)
                dx = 100 * abs(plus_di - minus_di) / max(plus_di + minus_di, 1e-9)
                if adx is None:
                    adx = dx
                else:
                    adx = (adx * 13 + dx) / 14
                atr = tr14 / 14
                adx_val = adx

        # Stochastic %K/%D
        stoch_k = None
        stoch_d = None
        if len(closes) >= 14:
            highest_high = max(highs[-14:])
            lowest_low = min(lows[-14:])
            if highest_high != lowest_low:
                stoch_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
                stoch_k_series.append(stoch_k)
                if len(stoch_k_series) >= 3:
                    stoch_d = sum(stoch_k_series[-3:]) / 3
        ret = None
        log_ret = None
        if len(closes) > 1:
            ret = (closes[-1] - closes[-2]) / closes[-2]
            log_ret = math.log(closes[-1] / closes[-2])

        if None in (
            sma_fast,
            sma_slow,
            ema_fast,
            ema_slow,
            rsi_val,
            ret,
            log_ret,
            macd_val,
            signal_val,
            hist_val,
            bb_mid,
            bb_upper,
            bb_lower,
            bb_width,
            atr,
            plus_di,
            minus_di,
            adx_val,
            stoch_k,
            stoch_d,
            vwap,
        ):
            continue
        rows.append(
            {
                "time": time_val,
                "close": close,
                "volume": volume,
                "vwap": vwap,
                "return": ret,
                "log_return": log_ret,
                "sma_fast": sma_fast,
                "sma_slow": sma_slow,
                "ema_fast": ema_fast,
                "ema_slow": ema_slow,
                "rsi": rsi_val,
                "macd": macd_val,
                "macd_signal": signal_val,
                "macd_hist": hist_val,
                "bb_mid": bb_mid,
                "bb_upper": bb_upper,
                "bb_lower": bb_lower,
                "bb_width": bb_width,
                "atr": atr,
                "plus_di": plus_di,
                "minus_di": minus_di,
                "adx": adx_val,
                "stoch_k": stoch_k,
                "stoch_d": stoch_d,
                "obv": obv,
            }
        )

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    print(f"wrote {len(rows)} feature rows to {args.output}")


if __name__ == "__main__":
    main()
