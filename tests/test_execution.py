from __future__ import annotations

import pytest

from oanda_autotrader.config import AppConfig, AppSettings
from oanda_autotrader.execution import (
    AccountSnapshot,
    PracticeExecutionEngine,
    RiskPolicy,
    TradeAction,
)


@pytest.fixture
def app_config() -> AppConfig:
    return AppConfig(
        group_name="demo",
        environment="practice",
        currency="CAD",
        account_name="Primary",
        account_type="primary",
        account_id="101-001-1234567-001",
        token="secret",
        base_url="https://api-fxpractice.oanda.com",
        stream_base_url="https://stream-fxpractice.oanda.com",
        settings=AppSettings(
            request_timeout_seconds=30,
            stream_timeout_seconds=0,
            reconnect=True,
            max_retries=None,
            backoff_base_seconds=0.5,
            backoff_max_seconds=15.0,
            requests_per_second=100,
            debug_logging=False,
        ),
    )


def test_engine_builds_buy_order_without_submitting(app_config: AppConfig) -> None:
    engine = PracticeExecutionEngine(
        app_config,
        RiskPolicy(allowed_instruments=("USD_CAD",), max_units_per_trade=100),
    )
    snapshot = AccountSnapshot(
        environment="practice",
        account_id=app_config.account_id,
        nav=10000.0,
        balance=10000.0,
        open_trade_count=0,
    )
    action = TradeAction(
        action="buy",
        instrument="USD_CAD",
        units=100,
        confidence=0.7,
        stop_loss_price="1.35000",
        take_profit_price="1.36000",
    )
    result = engine.execute(action, snapshot, dry_run=True)
    assert result["submitted"] is False
    assert result["order"]["units"] == "100"


def test_engine_rejects_live_execution(app_config: AppConfig) -> None:
    live_config = AppConfig(**{**app_config.__dict__, "environment": "live"})
    engine = PracticeExecutionEngine(
        live_config,
        RiskPolicy(allowed_instruments=("USD_CAD",)),
    )
    snapshot = AccountSnapshot(
        environment="live",
        account_id=live_config.account_id,
        nav=10000.0,
        balance=10000.0,
        open_trade_count=0,
    )
    action = TradeAction(
        action="buy",
        instrument="USD_CAD",
        units=100,
        confidence=0.7,
        stop_loss_price="1.35000",
    )
    with pytest.raises(ValueError):
        engine.execute(action, snapshot, dry_run=True)


def test_engine_builds_close_order_from_existing_position(app_config: AppConfig) -> None:
    engine = PracticeExecutionEngine(
        app_config,
        RiskPolicy(allowed_instruments=("USD_CAD",), max_units_per_trade=100),
    )
    snapshot = AccountSnapshot(
        environment="practice",
        account_id=app_config.account_id,
        nav=10000.0,
        balance=10000.0,
        open_trade_count=1,
        positions_by_instrument={"USD_CAD": 100},
    )
    action = TradeAction(
        action="close",
        instrument="USD_CAD",
        confidence=0.7,
    )
    result = engine.execute(action, snapshot, dry_run=True)
    assert result["submitted"] is False
    assert result["order"]["units"] == "-100"


def test_engine_rejects_projected_gross_exposure_over_cap(app_config: AppConfig) -> None:
    engine = PracticeExecutionEngine(
        app_config,
        RiskPolicy(allowed_instruments=("USD_CAD",), max_units_per_trade=100, max_gross_position_units=150),
    )
    snapshot = AccountSnapshot(
        environment="practice",
        account_id=app_config.account_id,
        nav=10000.0,
        balance=10000.0,
        open_trade_count=1,
        positions_by_instrument={"EUR_USD": 100},
    )
    action = TradeAction(
        action="buy",
        instrument="USD_CAD",
        units=100,
        confidence=0.7,
        stop_loss_price="1.35000",
    )
    with pytest.raises(ValueError, match="Gross position exposure limit reached"):
        engine.execute(action, snapshot, dry_run=True)


def test_engine_rejects_currency_concentration_over_cap(app_config: AppConfig) -> None:
    engine = PracticeExecutionEngine(
        app_config,
        RiskPolicy(
            allowed_instruments=("USD_CAD",),
            max_units_per_trade=100,
            max_gross_position_units=500,
            max_currency_gross_units=150,
        ),
    )
    snapshot = AccountSnapshot(
        environment="practice",
        account_id=app_config.account_id,
        nav=10000.0,
        balance=10000.0,
        open_trade_count=2,
        positions_by_instrument={"EUR_USD": 100, "GBP_USD": 100},
    )
    action = TradeAction(
        action="buy",
        instrument="USD_CAD",
        units=100,
        confidence=0.7,
        stop_loss_price="1.35000",
    )
    with pytest.raises(ValueError, match="Currency exposure limit reached"):
        engine.execute(action, snapshot, dry_run=True)


def test_engine_rejects_currency_correlation_over_cap(app_config: AppConfig) -> None:
    engine = PracticeExecutionEngine(
        app_config,
        RiskPolicy(
            allowed_instruments=("GBP_USD", "EUR_USD"),
            max_units_per_trade=100,
            max_gross_position_units=500,
            max_currency_gross_units=500,
            max_currency_positions=1,
        ),
    )
    snapshot = AccountSnapshot(
        environment="practice",
        account_id=app_config.account_id,
        nav=10000.0,
        balance=10000.0,
        open_trade_count=1,
        positions_by_instrument={"EUR_USD": 100},
    )
    action = TradeAction(
        action="buy",
        instrument="GBP_USD",
        units=100,
        confidence=0.7,
        stop_loss_price="1.35000",
    )
    with pytest.raises(ValueError, match="Currency correlation limit reached"):
        engine.execute(action, snapshot, dry_run=True)


def test_engine_project_snapshot_tracks_new_positions_and_closes(app_config: AppConfig) -> None:
    engine = PracticeExecutionEngine(
        app_config,
        RiskPolicy(allowed_instruments=("USD_CAD",), max_units_per_trade=100),
    )
    snapshot = AccountSnapshot(
        environment="practice",
        account_id=app_config.account_id,
        nav=10000.0,
        balance=10000.0,
        open_trade_count=1,
        positions_by_instrument={"USD_CAD": 100},
    )
    close_action = TradeAction(action="close", instrument="USD_CAD", confidence=0.7)
    closed = engine.project_snapshot(snapshot, close_action)
    assert closed.open_trade_count == 0
    assert closed.positions_by_instrument["USD_CAD"] == 0
    buy_action = TradeAction(
        action="buy",
        instrument="EUR_USD",
        units=100,
        confidence=0.7,
        stop_loss_price="1.10000",
    )
    projected = engine.project_snapshot(closed, buy_action)
    assert projected.open_trade_count == 1
    assert projected.positions_by_instrument["EUR_USD"] == 100


def test_engine_marks_market_halted_cancel_as_not_submitted(app_config: AppConfig) -> None:
    engine = PracticeExecutionEngine(
        app_config,
        RiskPolicy(allowed_instruments=("USD_CAD",), max_units_per_trade=100),
    )
    engine.orders.create_order = lambda _account_id, _order: {
        "orderCreateTransaction": {"id": "1", "type": "MARKET_ORDER"},
        "orderCancelTransaction": {"id": "2", "type": "ORDER_CANCEL", "reason": "MARKET_HALTED"},
    }
    snapshot = AccountSnapshot(
        environment="practice",
        account_id=app_config.account_id,
        nav=10000.0,
        balance=10000.0,
        open_trade_count=0,
    )
    action = TradeAction(
        action="sell",
        instrument="USD_CAD",
        units=100,
        confidence=0.7,
        stop_loss_price="1.35000",
    )

    result = engine.execute(action, snapshot, dry_run=False)

    assert result["submitted"] is False
    assert result["status"] == "canceled"
    assert result["cancel_reason"] == "MARKET_HALTED"


def test_engine_marks_filled_market_order_as_submitted(app_config: AppConfig) -> None:
    engine = PracticeExecutionEngine(
        app_config,
        RiskPolicy(allowed_instruments=("USD_CAD",), max_units_per_trade=100),
    )
    engine.orders.create_order = lambda _account_id, _order: {
        "orderCreateTransaction": {"id": "1", "type": "MARKET_ORDER"},
        "orderFillTransaction": {"id": "2", "type": "ORDER_FILL"},
    }
    snapshot = AccountSnapshot(
        environment="practice",
        account_id=app_config.account_id,
        nav=10000.0,
        balance=10000.0,
        open_trade_count=0,
    )
    action = TradeAction(
        action="sell",
        instrument="USD_CAD",
        units=100,
        confidence=0.7,
        stop_loss_price="1.35000",
    )

    result = engine.execute(action, snapshot, dry_run=False)

    assert result["submitted"] is True
    assert result["status"] == "filled"
    assert result["cancel_reason"] is None
