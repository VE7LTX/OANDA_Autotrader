from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timezone

from scripts.research_opportunity_patterns import (
    active_research_external_signals,
    apply_research_external_signals,
    iter_research_configs,
)


def base_args(**overrides):
    values = {
        "min_submit_scores": "5.4",
        "non_liquid_min_submit_scores": "6.0",
        "metal_submit_adds": "0.45",
        "commodity_submit_adds": "0.55",
        "max_spread_atr_ratios": "0.65",
        "entry_extension_atrs": "1.35",
        "htf_min_agreements": "1",
        "higher_timeframe_agreement_bonus": 0.35,
        "higher_timeframe_conflict_penalty": 0.60,
        "higher_timeframe_max_score_bonus": 0.75,
        "disable_entry_timing_confirmation": False,
        "disable_higher_timeframe_confirmation": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_disable_entry_timing_flag_generates_disabled_configs() -> None:
    configs = list(iter_research_configs(base_args(disable_entry_timing_confirmation=True)))

    assert configs
    assert {config["disable_entry_timing_confirmation"] for config in configs} == {True}


def test_disable_higher_timeframe_flag_generates_disabled_configs() -> None:
    configs = list(iter_research_configs(base_args(disable_higher_timeframe_confirmation=True)))

    assert configs
    assert {config["disable_higher_timeframe_confirmation"] for config in configs} == {True}


def test_active_research_external_signals_are_causal_and_fresh() -> None:
    signals = [
        {"_timestamp": datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc), "direction": "bullish"},
        {"_timestamp": datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc), "direction": "bullish"},
    ]

    active = active_research_external_signals(
        signals,
        candle_time=datetime(2026, 5, 1, 11, 0, tzinfo=timezone.utc),
        max_age_minutes=120,
    )

    assert active == [signals[0]]


def test_research_external_signal_conflict_can_block_candidate() -> None:
    candidate = {
        "instrument": "EUR_USD",
        "action": "buy",
        "score": 5.7,
        "required_score": 5.4,
        "metadata": {},
    }
    signals = {
        "EUR_USD": [
            {
                "_timestamp": datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
                "source": "test",
                "instrument": "EUR_USD",
                "direction": "bearish",
                "confidence": 1.0,
            }
        ]
    }

    adjustment = apply_research_external_signals(
        candidate,
        signals,
        candle_time=datetime(2026, 5, 1, 10, 30, tzinfo=timezone.utc),
        args=SimpleNamespace(external_signal_max_age_minutes=240, external_signal_max_adjustment=0.75),
    )

    assert adjustment == -0.75
    assert candidate["blocked_reason"] == "external_signal_conflict"
