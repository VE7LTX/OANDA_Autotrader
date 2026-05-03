from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from scripts.backtest_open_window import replay_window


def _candle(ts: str, price: float) -> dict:
    return {
        "time": ts,
        "mid": {
            "c": f"{price:.5f}",
            "h": f"{price + 0.0002:.5f}",
            "l": f"{price - 0.0002:.5f}",
        },
    }


def test_replay_window_returns_rows_for_requested_range() -> None:
    candles = []
    base_prices = [1.3500 + (i * 0.0001) for i in range(30)]
    start = datetime(2026, 4, 26, 19, 5, tzinfo=timezone.utc)
    for i, price in enumerate(base_prices):
        ts = (start + timedelta(minutes=i * 5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        candles.append(_candle(ts, price))

    args = SimpleNamespace(
        instrument="USD_CAD",
        fast_window=5,
        slow_window=20,
        units=100,
        max_units=100,
        max_open_trades=1,
        window_start="2026-04-26T21:05:00Z",
        window_end="2026-04-26T21:35:00Z",
        window_hours=48,
        risk_per_trade_fraction=0.0025,
        long_score_threshold=2.0,
        short_score_threshold=2.0,
        regime_score_threshold=1.0,
    )
    replay = replay_window(candles, args)
    assert replay["window_rows"]
    assert "action_counts" in replay
    assert "summary" in replay


def test_replay_window_uses_managed_exit_rules() -> None:
    candles = []
    prices = [1.3000 + (i * 0.0004) for i in range(18)]
    start = datetime(2026, 4, 26, 21, 0, tzinfo=timezone.utc)
    for i, price in enumerate(prices):
        ts = (start + timedelta(minutes=i * 5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        candles.append(_candle(ts, price))

    args = SimpleNamespace(
        instrument="USD_CAD",
        granularity="M5",
        fast_window=2,
        slow_window=5,
        units=100,
        max_units=100,
        max_open_trades=1,
        window_start="2026-04-26T22:10:00Z",
        window_end="2026-04-26T22:25:00Z",
        window_hours=48,
        fetch_count=100,
        risk_per_trade_fraction=0.0025,
        long_score_threshold=1.5,
        short_score_threshold=2.0,
        regime_score_threshold=0.5,
        trailing_atr_multiple=10.0,
        break_even_atr_multiple=10.0,
        max_hold_candles=1,
        spread_pips=0.0,
        slippage_pips=0.0,
        allowed_hours_utc="21,22,23",
    )
    replay = replay_window(candles, args)
    completed = replay["completed_trades"]
    assert completed
    assert any(trade["exit_reason"] == "max_hold_exit" for trade in completed)
