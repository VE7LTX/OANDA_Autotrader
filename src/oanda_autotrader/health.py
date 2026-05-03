"""
Cycle-level safety and health checks for the simple bot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .execution import AccountSnapshot, RiskPolicy, TradeAction


@dataclass(frozen=True)
class HealthCheckResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HealthConfig:
    min_candles: int = 20
    max_staleness_seconds: int = 900
    max_failures: int = 3
    min_atr: float = 0.00015
    max_daily_loss: float = 250.0
    max_weekly_loss: float = 750.0
    min_regime_score: float = 1.0
    allowed_hours_utc: tuple[int, ...] = tuple(range(0, 24))


def evaluate_bot_health(
    *,
    candles: list[dict],
    snapshot: AccountSnapshot,
    action: TradeAction,
    policy: RiskPolicy,
    failure_count: int,
    config: HealthConfig,
    latest_atr: float | None = None,
    daily_pnl: float = 0.0,
    weekly_pnl: float = 0.0,
    regime_score: float | None = None,
) -> HealthCheckResult:
    reasons: list[str] = []
    details: dict[str, Any] = {"failure_count": failure_count}
    action_name = action.action.lower()
    is_close = action_name == "close"

    if len(candles) < config.min_candles:
        reasons.append("not_enough_candles")

    stale_seconds = _stale_seconds(candles)
    details["stale_seconds"] = stale_seconds
    if stale_seconds is None:
        reasons.append("missing_candle_timestamp")
    elif stale_seconds > config.max_staleness_seconds:
        reasons.append("market_data_stale")

    if snapshot.open_trade_count > policy.max_open_trades and not is_close:
        reasons.append("open_trade_limit_exceeded")

    if failure_count >= config.max_failures:
        reasons.append("too_many_recent_failures")

    if action_name != "hold" and not policy.allows_instrument(action.instrument):
        reasons.append("instrument_not_allowed")

    details["daily_pnl"] = daily_pnl
    details["weekly_pnl"] = weekly_pnl
    if latest_atr is not None and not is_close:
        details["atr"] = latest_atr
        if latest_atr < config.min_atr:
            reasons.append("atr_too_low")
    if daily_pnl <= -abs(config.max_daily_loss) and not is_close:
        reasons.append("daily_loss_limit_hit")
    if weekly_pnl <= -abs(config.max_weekly_loss) and not is_close:
        reasons.append("weekly_loss_limit_hit")
    if regime_score is not None and not is_close:
        details["regime_score"] = regime_score
        if regime_score < config.min_regime_score:
            reasons.append("regime_filter_blocked")
    session_hour = _session_hour(candles)
    details["session_hour_utc"] = session_hour
    if session_hour is None:
        reasons.append("missing_session_hour")
    elif config.allowed_hours_utc and session_hour not in config.allowed_hours_utc and not is_close:
        reasons.append("outside_allowed_hours")

    return HealthCheckResult(ok=not reasons, reasons=reasons, details=details)


def _stale_seconds(candles: list[dict]) -> int | None:
    if not candles:
        return None
    raw = candles[-1].get("time")
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return int((datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds())


def _session_hour(candles: list[dict]) -> int | None:
    if not candles:
        return None
    raw = candles[-1].get("time")
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
    return ts.hour
