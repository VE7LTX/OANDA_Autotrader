from __future__ import annotations

from types import SimpleNamespace

from scripts.research_opportunity_patterns import iter_research_configs


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
