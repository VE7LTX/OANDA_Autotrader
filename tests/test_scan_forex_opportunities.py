from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import requests

import scripts.scan_forex_opportunities as scanner
from oanda_autotrader.execution import TradeAction

from scripts.scan_forex_opportunities import (
    apply_live_spread_guard,
    apply_adaptive_quality,
    build_decision_summary,
    build_trade_action,
    describe_exception,
    entry_throttle_reason,
    fetch_candles_safe,
    is_fx_pair,
    is_major_fx_pair,
    instrument_price_precisions,
    maybe_submit_candidates,
    non_liquid_trade_blocked,
    opportunity_score,
    rank_directional_watchlist,
    required_submit_score,
    select_scan_instruments,
    transaction_quality_from_transactions,
    update_instrument_quality,
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


def test_instrument_price_precisions_use_oanda_metadata() -> None:
    tradeable = [
        {"name": "GBP_JPY", "displayPrecision": 3},
        {"name": "HKD_JPY", "displayPrecision": 5},
        {"name": "XAU_USD", "displayPrecision": 3},
        {"name": "EUR_USD", "displayPrecision": "5"},
    ]

    assert instrument_price_precisions(tradeable) == {
        "EUR_USD": 5,
        "GBP_JPY": 3,
        "HKD_JPY": 5,
    }


def test_rank_directional_watchlist_includes_hold_pressure() -> None:
    candidates = [
        {"instrument": "EUR_USD", "action": "hold", "score": 1.0, "metadata": {"long_score": 1.2}},
        {"instrument": "GBP_USD", "action": "hold", "score": 0.5, "metadata": {"long_score": 2.8}},
        {"instrument": "AUD_USD", "action": "buy", "score": 5.0, "metadata": {"long_score": 2.8}},
    ]

    ranked = rank_directional_watchlist(candidates, "long_score")

    assert [item["instrument"] for item in ranked] == ["AUD_USD", "GBP_USD", "EUR_USD"]


def test_adaptive_quality_penalizes_bad_stats_but_recovers_with_atr() -> None:
    args = SimpleNamespace(
        disable_adaptive_quality=False,
        adaptive_min_atr_ratio=0.00012,
        adaptive_recovery_atr_ratio=0.00035,
        adaptive_max_avg_loss=0.05,
        adaptive_max_avg_half_spread_cost=0.05,
        adaptive_max_penalty=1.2,
    )
    quality = {"USD_HUF": {"closed_count": 5, "net_pl": -1.0, "fill_count": 5, "half_spread_cost": 0.6}}

    weak_score, weak_meta = apply_adaptive_quality(
        instrument="USD_HUF",
        score=5.6,
        latest_atr=0.01,
        latest_price=310.0,
        instrument_quality=quality,
        args=args,
    )
    recovered_score, recovered_meta = apply_adaptive_quality(
        instrument="USD_HUF",
        score=5.6,
        latest_atr=0.2,
        latest_price=310.0,
        instrument_quality=quality,
        args=args,
    )

    assert weak_score < 5.6
    assert "negative_recent_pl" in weak_meta["reasons"]
    assert "high_spread_cost" in weak_meta["reasons"]
    assert recovered_score > weak_score
    assert "atr_recovery" in recovered_meta["reasons"]


def test_adaptive_quality_penalizes_recent_decayed_losses() -> None:
    args = SimpleNamespace(
        disable_adaptive_quality=False,
        adaptive_min_atr_ratio=0.00012,
        adaptive_recovery_atr_ratio=0.00035,
        adaptive_max_avg_loss=0.05,
        adaptive_max_avg_half_spread_cost=0.05,
        adaptive_max_penalty=1.2,
    )
    quality = {"GBP_ZAR": {"closed_count": 1.6, "net_pl": -0.40, "fill_count": 1.6, "half_spread_cost": 0.03}}

    adjusted, meta = apply_adaptive_quality(
        instrument="GBP_ZAR",
        score=5.6,
        latest_atr=0.004,
        latest_price=22.5,
        instrument_quality=quality,
        args=args,
    )

    assert adjusted < 5.6
    assert "negative_recent_pl" in meta["reasons"]


def test_update_instrument_quality_ignores_canceled_orders() -> None:
    quality = update_instrument_quality(
        {},
        [
            {
                "instrument": "TRY_JPY",
                "action": "sell",
                "result": {"submitted": False, "status": "canceled", "cancel_reason": "MARKET_HALTED"},
            },
            {
                "instrument": "EUR_AUD",
                "action": "sell",
                "result": {
                    "submitted": True,
                    "response": {"orderFillTransaction": {"pl": "0.0", "halfSpreadCost": "0.02"}},
                },
            },
        ],
    )

    assert "TRY_JPY" not in quality
    assert quality["EUR_AUD"]["fill_count"] == 1.0


def test_update_instrument_quality_uses_slow_decay() -> None:
    quality = update_instrument_quality(
        {"GBP_ZAR": {"fill_count": 10, "closed_count": 8, "net_pl": -2.0, "half_spread_cost": 0.8}},
        [],
    )

    assert quality["GBP_ZAR"]["closed_count"] > 7.9
    assert quality["GBP_ZAR"]["net_pl"] < -1.99


def test_transaction_quality_seed_reads_broker_fills() -> None:
    quality = transaction_quality_from_transactions(
        [
            {
                "type": "ORDER_FILL",
                "instrument": "GBP_ZAR",
                "halfSpreadCost": "0.20",
                "pl": "-0.45",
                "tradesClosed": [{"tradeID": "1"}],
            },
            {
                "type": "ORDER_CANCEL",
                "instrument": "GBP_ZAR",
            },
        ]
    )

    assert quality["GBP_ZAR"]["fill_count"] == 1.0
    assert quality["GBP_ZAR"]["closed_count"] == 1.0
    assert quality["GBP_ZAR"]["net_pl"] == -0.45
    assert quality["GBP_ZAR"]["half_spread_cost"] == 0.20


def test_live_spread_guard_blocks_when_spread_over_atr() -> None:
    args = SimpleNamespace(max_spread_atr_ratio=0.5, min_exit_spread_multiple=1.25)
    action = TradeAction(
        action="buy",
        instrument="GBP_ZAR",
        units=100,
        confidence=0.6,
        stop_loss_price="22.50000",
        take_profit_price="22.56000",
    )

    result = apply_live_spread_guard(
        {"instrument": "GBP_ZAR", "atr": 0.01, "stop_loss_price": "22.50000", "take_profit_price": "22.56000"},
        action,
        {"bid": 22.53000, "ask": 22.54000, "spread": 0.01},
        args,
    )

    assert result["blocked_reason"] == "live_spread_too_wide"


def test_live_spread_guard_widens_exits_away_from_bid_ask() -> None:
    args = SimpleNamespace(max_spread_atr_ratio=2.0, min_exit_spread_multiple=1.25)
    action = TradeAction(
        action="buy",
        instrument="EUR_USD",
        units=100,
        confidence=0.6,
        stop_loss_price="1.09999",
        take_profit_price="1.10003",
    )

    result = apply_live_spread_guard(
        {"instrument": "EUR_USD", "atr": 0.001, "stop_loss_price": "1.09999", "take_profit_price": "1.10003"},
        action,
        {"bid": 1.10000, "ask": 1.10002, "spread": 0.00002},
        args,
    )

    assert result["adjusted"] is True
    adjusted = result["action"]
    assert float(adjusted.take_profit_price) > 1.10002
    assert float(adjusted.stop_loss_price) < 1.10000


def test_required_submit_score_is_higher_for_non_liquid_pairs() -> None:
    args = SimpleNamespace(min_submit_score=5.4, non_liquid_min_submit_score=6.2)

    assert required_submit_score("EUR_USD", args) == 5.4
    assert required_submit_score("CHF_ZAR", args) == 6.2


def test_non_liquid_trade_gate_blocks_exotics_by_default() -> None:
    args = SimpleNamespace(allow_non_liquid_trades=False)
    permissive_args = SimpleNamespace(allow_non_liquid_trades=True)

    assert non_liquid_trade_blocked("CHF_ZAR", args) is True
    assert non_liquid_trade_blocked("EUR_USD", args) is False
    assert non_liquid_trade_blocked("CHF_ZAR", permissive_args) is False


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


def test_describe_exception_compacts_large_response_body() -> None:
    response = requests.Response()
    response.status_code = 504
    response._content = ("<html>\n" + ("x" * 1000) + "\n</html>").encode()
    exc = requests.HTTPError("504 Server Error", response=response)

    description = describe_exception(exc)

    assert "\n" not in description
    assert len(description) < 520
    assert description.endswith("...")


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
    args = SimpleNamespace(min_submit_score=5.4, non_liquid_min_submit_score=6.2, allow_non_liquid_trades=False)
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
    args = SimpleNamespace(min_submit_score=5.4, non_liquid_min_submit_score=6.2, allow_non_liquid_trades=False)
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
    args = SimpleNamespace(min_submit_score=5.4, non_liquid_min_submit_score=6.2, allow_non_liquid_trades=False)
    submissions = [
        {"instrument": "GBP_USD", "result": {"submitted": True}},
        {"instrument": "NZD_JPY", "result": {"submitted": True}},
    ]

    summary = build_decision_summary([], submissions, args)

    assert summary["decision"] == "submitted"
    assert summary["submitted_count"] == 2
    assert summary["instruments"] == ["GBP_USD", "NZD_JPY"]


def test_decision_summary_reports_best_watched_candidate() -> None:
    args = SimpleNamespace(min_submit_score=5.4, non_liquid_min_submit_score=6.2, allow_non_liquid_trades=False)
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


def test_decision_summary_reports_non_liquid_block() -> None:
    args = SimpleNamespace(min_submit_score=5.4, non_liquid_min_submit_score=6.2, allow_non_liquid_trades=False)
    candidates = [
        {
            "instrument": "CHF_ZAR",
            "action": "sell",
            "score": 6.5,
            "reason": "short_score_passed",
            "metadata": {"short_score": 3.2},
        }
    ]

    summary = build_decision_summary(candidates, [], args)

    assert summary["reason"] == "non_liquid_trade_disabled"
    assert summary["required_score"] == 6.2


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
        allow_non_liquid_trades=False,
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
