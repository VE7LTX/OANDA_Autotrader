from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import requests

import scripts.scan_forex_opportunities as scanner
from oanda_autotrader.execution import TradeAction

from scripts.scan_forex_opportunities import (
    build_trade_action,
    describe_exception,
    entry_throttle_reason,
    fetch_candles_safe,
    is_fx_pair,
    is_major_fx_pair,
    opportunity_score,
)


def test_opportunity_score_prefers_stronger_trade_signal() -> None:
    buy = opportunity_score(
        "buy",
        {"long_score": 3.0, "short_score": 1.0, "regime_score": 1.5, "separation": 0.0002, "rsi": 60},
        0.0002,
    )
    hold = opportunity_score(
        "hold",
        {"long_score": 1.0, "short_score": 1.0, "regime_score": 1.0, "separation": 0.00001, "rsi": 50},
        0.00005,
    )
    assert buy > hold


def test_is_fx_pair_excludes_non_currency_symbols() -> None:
    assert is_fx_pair("GBP_USD") is True
    assert is_fx_pair("XAU_NZD") is False


def test_is_major_fx_pair_filters_liquidity() -> None:
    assert is_major_fx_pair("GBP_USD") is True
    assert is_major_fx_pair("EUR_GBP") is True
    assert is_major_fx_pair("EUR_NOK") is False


def test_build_trade_action_preserves_close_actions() -> None:
    action = build_trade_action(
        {
            "instrument": "GBP_USD",
            "action": "close",
            "reason": "managed_close_short",
            "units": 100,
            "confidence": 0.75,
            "metadata": {},
        }
    )
    assert action.action == "close"
    assert action.units == 100


def test_evaluate_managed_exit_closes_on_forced_reversal(monkeypatch) -> None:
    def fake_strategy(_candles, _strategy, _snapshot):
        return TradeAction(
            action="buy",
            instrument="GBP_USD",
            confidence=0.8,
            reason="forced_reversal",
            metadata={
                "current_units": -100,
                "long_score": 2.5,
                "short_score": 0.4,
                "regime_score": 1.4,
                "fast_ma": 1.0,
                "slow_ma": 0.9,
                "rsi": 55.0,
            },
        )

    monkeypatch.setattr(scanner, "moving_average_crossover", fake_strategy)
    monkeypatch.setattr(scanner, "atr", lambda _candles, _period: 0.001)
    result = scanner.evaluate_managed_exit(
        "GBP_USD",
        -100,
        [{"mid": {"c": "1.0"}}],
        SimpleNamespace(),
        scanner.StrategyConfig(instrument="GBP_USD"),
    )
    assert result is not None
    assert result["action"] == "close"
    assert result["kind"] == "exit"
    assert result["reason"] == "managed_close_short"


def test_fetch_candles_safe_records_and_skips_failures() -> None:
    class BrokenClient:
        def get_candles(self, *_args, **_kwargs):
            raise RuntimeError("gateway timeout")

    errors = []
    result = fetch_candles_safe(BrokenClient(), "NZD_CAD", granularity="M5", count=120, errors=errors)

    assert result is None
    assert errors == [{"instrument": "NZD_CAD", "stage": "candles", "error": "gateway timeout"}]


def test_describe_exception_includes_response_body() -> None:
    response = requests.Response()
    response.status_code = 400
    response._content = b'{"errorMessage":"bad stop loss"}'
    exc = requests.HTTPError("400 Client Error", response=response)

    description = describe_exception(exc)

    assert "bad stop loss" in description
    assert "response=400" in description


def test_entry_throttle_stops_after_session_loss() -> None:
    args = SimpleNamespace(
        max_session_loss=1.0,
        max_trades_per_hour=2,
        instrument_cooldown_minutes=180,
        currency_cooldown_minutes=60,
    )
    action = TradeAction(action="sell", instrument="EUR_USD", units=100)

    assert entry_throttle_reason(action, [], args, realized_pnl_day=-1.01) == "session_loss_limit"


def test_entry_throttle_limits_recent_activity() -> None:
    args = SimpleNamespace(
        max_session_loss=10.0,
        max_trades_per_hour=2,
        instrument_cooldown_minutes=180,
        currency_cooldown_minutes=60,
    )
    now = datetime.now(timezone.utc)
    recent = [
        {"timestamp": (now - timedelta(minutes=10)).isoformat(), "instrument": "EUR_USD"},
        {"timestamp": (now - timedelta(minutes=20)).isoformat(), "instrument": "GBP_USD"},
    ]
    action = TradeAction(action="sell", instrument="AUD_USD", units=100)

    assert entry_throttle_reason(action, recent, args, realized_pnl_day=0.0) == "max_trades_per_hour"


def test_entry_throttle_limits_same_instrument() -> None:
    args = SimpleNamespace(
        max_session_loss=10.0,
        max_trades_per_hour=5,
        instrument_cooldown_minutes=180,
        currency_cooldown_minutes=0,
    )
    recent = [{"timestamp": datetime.now(timezone.utc).isoformat(), "instrument": "EUR_USD"}]
    action = TradeAction(action="sell", instrument="EUR_USD", units=100)

    assert entry_throttle_reason(action, recent, args, realized_pnl_day=0.0) == "instrument_cooldown"


def test_entry_throttle_limits_currency_family() -> None:
    args = SimpleNamespace(
        max_session_loss=10.0,
        max_trades_per_hour=5,
        instrument_cooldown_minutes=0,
        currency_cooldown_minutes=60,
    )
    recent = [{"timestamp": datetime.now(timezone.utc).isoformat(), "instrument": "EUR_USD"}]
    action = TradeAction(action="sell", instrument="USD_JPY", units=100)

    assert entry_throttle_reason(action, recent, args, realized_pnl_day=0.0) == "currency_cooldown"
