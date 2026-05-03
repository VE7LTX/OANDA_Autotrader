from __future__ import annotations

from oanda_autotrader.execution import AccountSnapshot, RiskPolicy, TradeAction
from oanda_autotrader.health import HealthConfig, evaluate_bot_health
from oanda_autotrader.state import BotState


def test_health_blocks_daily_loss_limit() -> None:
    candles = [{"time": "2026-05-04T21:10:00Z", "mid": {"c": "1.35000"}} for _ in range(25)]
    snapshot = AccountSnapshot(
        environment="practice",
        account_id="abc",
        nav=10000.0,
        balance=10000.0,
        open_trade_count=0,
    )
    action = TradeAction(action="buy", instrument="USD_CAD", units=10, confidence=0.8, stop_loss_price="1.3490")
    result = evaluate_bot_health(
        candles=candles,
        snapshot=snapshot,
        action=action,
        policy=RiskPolicy(allowed_instruments=("USD_CAD",)),
        failure_count=0,
        config=HealthConfig(min_candles=20, max_staleness_seconds=10**9, max_daily_loss=100.0),
        latest_atr=0.0002,
        daily_pnl=-150.0,
        weekly_pnl=0.0,
    )
    assert "daily_loss_limit_hit" in result.reasons


def test_state_tracks_realized_pnl() -> None:
    state = BotState()
    state.open_trade(side="long", units=100, entry_price=1.3500, instrument="USD_CAD")
    pnl = state.close_trade(exit_price=1.3510)
    assert pnl is not None
    assert state.realized_pnl_day > 0
