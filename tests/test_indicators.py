from __future__ import annotations

from oanda_autotrader.indicators import atr, ema, extract_closes, rsi


def _candle(close: float, high: float | None = None, low: float | None = None) -> dict:
    return {
        "mid": {
            "c": f"{close:.5f}",
            "h": f"{(high if high is not None else close + 0.0002):.5f}",
            "l": f"{(low if low is not None else close - 0.0002):.5f}",
        }
    }


def test_indicator_helpers() -> None:
    closes = [1.35 + (i * 0.0001) for i in range(20)]
    candles = [_candle(v) for v in closes]
    assert extract_closes(candles)[0] == closes[0]
    assert ema(closes, 5) > 0
    assert 0 <= rsi(closes, 14) <= 100
    assert atr(candles, 14) > 0
