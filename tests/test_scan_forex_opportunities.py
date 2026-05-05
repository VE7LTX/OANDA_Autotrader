from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import requests

import scripts.scan_forex_opportunities as scanner
from oanda_autotrader.execution import TradeAction

from scripts.scan_forex_opportunities import (
    build_decision_summary,
    build_trade_action,
    describe_exception,
    entry_throttle_reason,
    fetch_candles_safe,
    is_fx_pair,
    is_major_fx_pair,
    maybe_submit_candidates,
    opportunity_score,
    rank_directional_watchlist,
    required_submit_score,
    select_scan_instruments,
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


def test_select_scan_instruments_defaults_to_all_tradeable_fx() -> None:
    tradeable = [
        {"name": "EUR_USD"},
        {"name": "EUR_NOK"},
        {"name": "XAU_USD"},
        {"name": "GBP_USD"},
        {"name": "EUR_USD"},
    ]

    assert select_scan_instruments(tradeable, majors_only=False) == ["EUR_NOK", "EUR_USD", "GBP_USD"]
    assert select_scan_instruments(tradeable, majors_only=True) == ["EUR_USD", "GBP_USD"]


def test_rank_directional_watchlist_includes_hold_pressure() -> None:
    candidates = [
        {"instrument": "EUR_USD", "action": "hold", "score": 1.0, "metadata": {"long_score": 1.2}},
        {"instrument": "GBP_USD", "action": "hold", "score": 0.5, "metadata": {"long_score": 2.8}},
        {"instrument": "AUD_USD", "action": "buy", "score": 5.0, "metadata": {"long_score": 2.8}},
    ]

    ranked = rank_directional_watchlist(candidates, "long_score")

    assert [item["instrument"] for item in ranked] == ["AUD_USD", "GBP_USD", "EUR_USD"]


def test_required_submit_score_is_higher_for_non_liquid_pairs() -> None:
    args = SimpleNamespace(min_submit_score=5.4, non_liquid_min_submit_score=6.2)

    assert required_submit_score("EUR_USD", args) == 5.4
    assert required_submit_score("CHF_ZAR", args) == 6.2


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


def test_decision_summary_reports_below_threshold() -> None:
    args = SimpleNamespace(min_submit_score=5.4, non_liquid_min_submit_score=6.2)
    candidates = [
        {
            "instrument": "NZD_JPY",
            "action": "sell",
            "score": 5.2,
            "reason": "short_score_passed",
            "metadata": {"short_score": 2.85, "fib_retracement": 0.5},
        }
    ]

    summary = build_decision_summary(candidates, [], args)

    assert summary["decision"] == "watching"
    assert summary["reason"] == "below_submit_threshold"
    assert summary["score_gap"] == 0.20000000000000018
    assert summary["required_score"] == 5.4
    assert summary["filter_reason"] == "short_score_passed"
    assert summary["short_score"] == 2.85
    assert summary["fib_retracement"] == 0.5


def test_decision_summary_reports_blocked_candidate() -> None:
    args = SimpleNamespace(min_submit_score=5.4, non_liquid_min_submit_score=6.2)
    candidates = [
        {
            "instrument": "USD_JPY",
            "action": "sell",
            "score": 5.8,
            "blocked_reason": "currency_cooldown",
        }
    ]

    summary = build_decision_summary(candidates, [], args)

    assert summary["decision"] == "watching"
    assert summary["reason"] == "currency_cooldown"


def test_decision_summary_reports_submissions() -> None:
    args = SimpleNamespace(min_submit_score=5.4, non_liquid_min_submit_score=6.2)
    submissions = [
        {"instrument": "GBP_USD", "result": {"submitted": True}},
        {"instrument": "NZD_JPY", "result": {"submitted": True}},
    ]

    summary = build_decision_summary([], submissions, args)

    assert summary["decision"] == "submitted"
    assert summary["submitted_count"] == 2
    assert summary["instruments"] == ["GBP_USD", "NZD_JPY"]


def test_decision_summary_reports_best_watched_candidate() -> None:
    args = SimpleNamespace(min_submit_score=5.4, non_liquid_min_submit_score=6.2)
    candidates = [
        {
            "instrument": "USD_JPY",
            "action": "hold",
            "score": 2.26,
            "reason": "regime_filter_hold",
            "metadata": {"long_score": 1.1, "short_score": 2.85, "regime_score": 1.1, "rsi": 42.0},
        },
        {
            "instrument": "EUR_NZD",
            "action": "hold",
            "score": 1.2,
            "reason": "score_below_threshold",
            "metadata": {"long_score": 2.0, "short_score": 0.75, "regime_score": 0.6, "rsi": 66.0},
        },
    ]

    summary = build_decision_summary(candidates, [], args)

    assert summary["decision"] == "watching"
    assert summary["reason"] == "no_actionable_candidates"
    assert summary["instrument"] == "USD_JPY"
    assert summary["filter_reason"] == "regime_filter_hold"
    assert summary["short_score"] == 2.85


def test_close_candidates_bypass_entry_submit_threshold(monkeypatch) -> None:
    class FakeEngine:
        policy = SimpleNamespace(
            max_open_trades=5,
            max_gross_position_units=500,
            max_currency_gross_units=500,
            max_currency_positions=2,
        )

        def __init__(self, *args, **kwargs) -> None:
            pass

        def execute(self, action, snapshot, *, dry_run):
            return {"submitted": True, "dry_run": dry_run, "order": {"units": str(action.units)}}

        def project_snapshot(self, snapshot, action):
            return snapshot

    monkeypatch.setattr("scripts.scan_forex_opportunities.PracticeExecutionEngine", FakeEngine)
    args = SimpleNamespace(
        min_submit_score=5.4,
        non_liquid_min_submit_score=6.2,
        max_units=100,
        max_open_trades=5,
        max_gross_position_units=500,
        max_currency_gross_units=500,
        max_currency_positions=2,
        max_new_trades=5,
        state_path="missing-state.json",
    )
    app_config = SimpleNamespace(environment="practice")
    snapshot = SimpleNamespace(open_trade_count=1, positions_by_instrument={"GBP_USD": -100})
    candidates = [
        {
            "instrument": "GBP_USD",
            "action": "close",
            "score": 1.0,
            "reason": "managed_exit",
            "units": 100,
        }
    ]

    submissions = maybe_submit_candidates(
        app_config=app_config,
        snapshot=snapshot,
        candidates=candidates,
        args=args,
    )

    assert submissions[0]["action"] == "close"
    assert submissions[0]["result"]["submitted"] is True
