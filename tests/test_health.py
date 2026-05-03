from __future__ import annotations

from oanda_autotrader.execution import AccountSnapshot, RiskPolicy, TradeAction
from oanda_autotrader.health import HealthConfig, evaluate_bot_health


def test_health_blocks_stale_data() -> None:
    candles = [{"time": "2020-01-01T00:00:00Z", "mid": {"c": "1.35000"}} for _ in range(20)]
    snapshot = AccountSnapshot(
        environment="practice",
        account_id="abc",
        nav=10000.0,
        balance=10000.0,
        open_trade_count=0,
    )
    action = TradeAction(action="hold", instrument="USD_CAD")
    result = evaluate_bot_health(
        candles=candles,
        snapshot=snapshot,
        action=action,
        policy=RiskPolicy(allowed_instruments=("USD_CAD",)),
        failure_count=0,
        config=HealthConfig(min_candles=20, max_staleness_seconds=60),
        latest_atr=0.0002,
        daily_pnl=0.0,
        weekly_pnl=0.0,
    )
    assert result.ok is False
    assert "market_data_stale" in result.reasons
