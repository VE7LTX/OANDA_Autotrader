"""
Deterministic scored strategy with ATR-based sizing.
"""

from __future__ import annotations

from dataclasses import dataclass

from .execution import AccountSnapshot, TradeAction
from .indicators import atr, ema, extract_closes, extract_highs, extract_lows, rsi


@dataclass(frozen=True)
class StrategyConfig:
    instrument: str
    fast_window: int = 5
    slow_window: int = 20
    units: int = 100
    min_separation: float = 0.0001
    atr_period: int = 14
    atr_stop_multiple: float = 1.5
    atr_target_multiple: float = 2.5
    risk_per_trade_fraction: float = 0.0025
    long_score_threshold: float = 2.25
    short_score_threshold: float = 2.0
    regime_score_threshold: float = 1.0
    trailing_atr_multiple: float = 1.25
    max_hold_candles: int = 24
    break_even_atr_multiple: float = 1.0
    fib_lookback: int = 55


def moving_average_crossover(
    candles: list[dict], config: StrategyConfig, snapshot: AccountSnapshot | None = None
) -> TradeAction:
    closes = extract_closes(candles)
    min_history = max(config.slow_window, config.atr_period + 1)
    if len(closes) < min_history:
        return TradeAction(action="hold", instrument=config.instrument, reason="not_enough_candles")

    fast_ma = ema(closes, config.fast_window)
    slow_ma = ema(closes, config.slow_window)
    last_price = closes[-1]
    separation = abs(fast_ma - slow_ma)
    latest_atr = atr(candles, config.atr_period)
    latest_rsi = rsi(closes, min(14, len(closes) - 1))
    fib_ratio = retracement_ratio(candles, lookback=config.fib_lookback)
    current_units = 0
    nav = 100000.0
    if snapshot is not None:
        current_units = snapshot.positions_by_instrument.get(config.instrument, 0)
        nav = snapshot.nav or nav

    long_score = score_long(fast_ma, slow_ma, separation, latest_rsi, latest_atr, last_price, fib_ratio)
    short_score = score_short(fast_ma, slow_ma, separation, latest_rsi, latest_atr, last_price, fib_ratio)
    regime_score = score_regime(separation, latest_atr, last_price)
    units = position_size_from_atr(
        nav=nav,
        atr_value=latest_atr,
        risk_fraction=config.risk_per_trade_fraction,
        atr_stop_multiple=config.atr_stop_multiple,
        max_units=config.units,
    )
    common_meta = {
        "fast_ma": fast_ma,
        "slow_ma": slow_ma,
        "separation": separation,
        "current_units": current_units,
        "long_score": long_score,
        "short_score": short_score,
        "regime_score": regime_score,
        "atr": latest_atr,
        "rsi": latest_rsi,
        "fib_retracement": fib_ratio,
    }

    if regime_score < config.regime_score_threshold:
        if current_units != 0 and separation < config.min_separation:
            if current_units > 0 and fast_ma < slow_ma:
                return TradeAction(action="close", instrument=config.instrument, confidence=0.65, reason="regime_break_close_long", metadata=common_meta)
            if current_units < 0 and fast_ma > slow_ma:
                return TradeAction(action="close", instrument=config.instrument, confidence=0.65, reason="regime_break_close_short", metadata=common_meta)
        return TradeAction(action="hold", instrument=config.instrument, reason="regime_filter_hold", metadata=common_meta)

    if separation < config.min_separation:
        if current_units > 0 and fast_ma < slow_ma:
            return TradeAction(action="close", instrument=config.instrument, confidence=0.7, reason="trend_reversal_close_long", metadata=common_meta)
        if current_units < 0 and fast_ma > slow_ma:
            return TradeAction(action="close", instrument=config.instrument, confidence=0.7, reason="trend_reversal_close_short", metadata=common_meta)
        return TradeAction(action="hold", instrument=config.instrument, reason="moving_averages_too_close", metadata=common_meta)

    if long_score >= config.long_score_threshold and long_score > short_score:
        if current_units > 0:
            return TradeAction(action="hold", instrument=config.instrument, reason="existing_long_position", metadata=common_meta)
        if current_units < 0:
            return TradeAction(action="close", instrument=config.instrument, confidence=0.75, reason="close_short_before_long", metadata=common_meta)
        return TradeAction(
            action="buy",
            instrument=config.instrument,
            units=units,
            confidence=0.6,
            reason="long_score_passed",
            stop_loss_price=f"{last_price - (latest_atr * config.atr_stop_multiple):.5f}",
            take_profit_price=f"{last_price + (latest_atr * config.atr_target_multiple):.5f}",
            metadata=common_meta,
        )

    if short_score >= config.short_score_threshold and short_score > long_score:
        if current_units < 0:
            return TradeAction(action="hold", instrument=config.instrument, reason="existing_short_position", metadata=common_meta)
        if current_units > 0:
            return TradeAction(action="close", instrument=config.instrument, confidence=0.75, reason="close_long_before_short", metadata=common_meta)
        return TradeAction(
            action="sell",
            instrument=config.instrument,
            units=units,
            confidence=0.6,
            reason="short_score_passed",
            stop_loss_price=f"{last_price + (latest_atr * config.atr_stop_multiple):.5f}",
            take_profit_price=f"{last_price - (latest_atr * config.atr_target_multiple):.5f}",
            metadata=common_meta,
        )

    if current_units > 0 and long_score < 0.5:
        return TradeAction(action="close", instrument=config.instrument, confidence=0.55, reason="long_score_decay", metadata=common_meta)
    if current_units < 0 and short_score < 0.5:
        return TradeAction(action="close", instrument=config.instrument, confidence=0.55, reason="short_score_decay", metadata=common_meta)
    return TradeAction(action="hold", instrument=config.instrument, reason="score_below_threshold", metadata=common_meta)


def score_long(
    fast_ma: float,
    slow_ma: float,
    separation: float,
    latest_rsi: float,
    latest_atr: float,
    price: float,
    fib_ratio: float | None = None,
) -> float:
    score = 0.0
    if fast_ma > slow_ma:
        score += 1.25
    if separation / max(price, 1e-9) > 0.00005:
        score += 0.75
    if 55 <= latest_rsi <= 66:
        score += 0.5
    if latest_rsi > 72:
        score -= 0.5
    if latest_atr / max(price, 1e-9) > 0.00012:
        score += 0.35
    if fast_ma > slow_ma and fib_ratio is not None and 0.382 <= fib_ratio <= 0.618:
        score += 0.35
    return score


def score_short(
    fast_ma: float,
    slow_ma: float,
    separation: float,
    latest_rsi: float,
    latest_atr: float,
    price: float,
    fib_ratio: float | None = None,
) -> float:
    score = 0.0
    if fast_ma < slow_ma:
        score += 1.25
    if separation / max(price, 1e-9) > 0.00005:
        score += 0.75
    if 34 <= latest_rsi <= 45:
        score += 0.5
    if latest_rsi < 28:
        score -= 0.5
    if latest_atr / max(price, 1e-9) > 0.00012:
        score += 0.35
    if fast_ma < slow_ma and fib_ratio is not None and 0.382 <= fib_ratio <= 0.618:
        score += 0.35
    return score


def score_regime(separation: float, latest_atr: float, price: float) -> float:
    score = 0.0
    if separation / max(price, 1e-9) > 0.00005:
        score += 0.6
    if separation / max(price, 1e-9) > 0.0001:
        score += 0.4
    if latest_atr / max(price, 1e-9) > 0.00012:
        score += 0.5
    if latest_atr / max(price, 1e-9) > 0.0002:
        score += 0.5
    return score


def position_size_from_atr(*, nav: float, atr_value: float, risk_fraction: float, atr_stop_multiple: float, max_units: int) -> int:
    risk_budget = max(nav, 0.0) * max(risk_fraction, 0.0)
    stop_distance = max(atr_value * atr_stop_multiple, 1e-6)
    units = int(risk_budget / stop_distance)
    return max(1, min(max_units, units))


def retracement_ratio(candles: list[dict], *, lookback: int = 55) -> float | None:
    highs = extract_highs(candles[-lookback:])
    lows = extract_lows(candles[-lookback:])
    closes = extract_closes(candles[-lookback:])
    if not highs or not lows or not closes:
        return None
    swing_high = max(highs)
    swing_low = min(lows)
    swing_range = swing_high - swing_low
    if swing_range <= 0:
        return None
    return max(0.0, min(1.0, (closes[-1] - swing_low) / swing_range))
