from __future__ import annotations

from oanda_autotrader.execution import AccountSnapshot
from oanda_autotrader.strategy import (
    StrategyConfig,
    format_instrument_price,
    moving_average_crossover,
    projected_target_distance,
    retracement_ratio,
    score_long,
)


def _candle(price: float, ts: str = "2026-05-03T19:00:00Z") -> dict:
    return {
        "time": ts,
        "mid": {
            "c": f"{price:.5f}",
            "h": f"{price + 0.0002:.5f}",
            "l": f"{price - 0.0002:.5f}",
        },
    }


def test_strategy_holds_without_enough_candles() -> None:
    action = moving_average_crossover(
        [_candle(1.35) for _ in range(5)],
        StrategyConfig(instrument="USD_CAD", slow_window=20),
    )
    assert action.action == "hold"
    assert action.reason == "not_enough_candles"


def test_strategy_holds_when_atr_history_is_missing() -> None:
    action = moving_average_crossover(
        [_candle(1.35 + (i * 0.0001)) for i in range(10)],
        StrategyConfig(instrument="USD_CAD", slow_window=5, atr_period=14),
    )
    assert action.action == "hold"
    assert action.reason == "not_enough_candles"


def test_strategy_buys_when_fast_above_slow() -> None:
    candles = [_candle(1.30 + (i * 0.001)) for i in range(25)]
    action = moving_average_crossover(
        candles,
        StrategyConfig(
            instrument="USD_CAD",
            fast_window=5,
            slow_window=20,
            units=100,
            long_score_threshold=1.5,
        ),
    )
    assert action.action == "buy"
    assert action.units > 0
    assert action.metadata["risk_reward_ratio"] >= 2.0


def test_projected_target_distance_enforces_minimum_risk_reward() -> None:
    target = projected_target_distance(
        latest_atr=0.001,
        stop_distance=0.0015,
        fast_ma=1.1000,
        slow_ma=1.1001,
        score=2.0,
        min_risk_reward_ratio=2.0,
        atr_target_multiple=2.5,
    )

    assert target == 0.003


def test_strategy_holds_when_already_long() -> None:
    candles = [_candle(1.30 + (i * 0.001)) for i in range(25)]
    snapshot = AccountSnapshot(
        environment="practice",
        account_id="abc",
        nav=10000.0,
        balance=10000.0,
        open_trade_count=1,
        positions_by_instrument={"USD_CAD": 100},
    )
    action = moving_average_crossover(
        candles,
        StrategyConfig(
            instrument="USD_CAD",
            fast_window=5,
            slow_window=20,
            units=100,
            long_score_threshold=1.5,
        ),
        snapshot,
    )
    assert action.action == "hold"
    assert action.reason == "existing_long_position"


def test_strategy_closes_long_before_short() -> None:
    candles = [_candle(1.40 - (i * 0.0015)) for i in range(25)]
    snapshot = AccountSnapshot(
        environment="practice",
        account_id="abc",
        nav=10000.0,
        balance=10000.0,
        open_trade_count=1,
        positions_by_instrument={"USD_CAD": 100},
    )
    action = moving_average_crossover(
        candles,
        StrategyConfig(
            instrument="USD_CAD",
            fast_window=5,
            slow_window=20,
            units=100,
            short_score_threshold=1.5,
        ),
        snapshot,
    )
    assert action.action == "close"
    assert action.reason == "close_long_before_short"


def test_strategy_formats_jpy_prices_to_three_decimals() -> None:
    candles = [_candle(200.0 - (i * 0.01)) for i in range(25)]

    action = moving_average_crossover(
        candles,
        StrategyConfig(
            instrument="GBP_JPY",
            fast_window=5,
            slow_window=20,
            units=100,
            short_score_threshold=1.5,
        ),
    )

    assert action.action == "sell"
    assert action.stop_loss_price is not None
    assert len(action.stop_loss_price.rsplit(".", 1)[1]) == 3
    assert action.take_profit_price is not None
    assert len(action.take_profit_price.rsplit(".", 1)[1]) == 3


def test_format_instrument_price_uses_pair_precision() -> None:
    assert format_instrument_price("GBP_JPY", 212.69071) == "212.691"
    assert format_instrument_price("HKD_JPY", 16.123456, 5) == "16.12346"
    assert format_instrument_price("EUR_USD", 1.123456) == "1.12346"


def test_strategy_records_fib_retracement_metadata() -> None:
    candles = [_candle(1.30 + (i * 0.001)) for i in range(25)]

    action = moving_average_crossover(
        candles,
        StrategyConfig(instrument="USD_CAD", fast_window=5, slow_window=20, units=100),
    )

    assert action.metadata is not None
    assert 0.0 <= action.metadata["fib_retracement"] <= 1.0


def test_retracement_ratio_uses_recent_swing_range() -> None:
    candles = [_candle(1.00), _candle(1.10), _candle(1.05)]

    ratio = retracement_ratio(candles, lookback=3)

    assert ratio is not None
    assert 0.40 < ratio < 0.60


def test_fib_zone_adds_confluence_without_overriding_trend() -> None:
    baseline = score_long(1.01, 1.00, 0.01, 60.0, 0.001, 1.02, None)
    confluence = score_long(1.01, 1.00, 0.01, 60.0, 0.001, 1.02, 0.5)

    assert confluence > baseline
