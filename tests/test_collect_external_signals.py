from __future__ import annotations

from scripts.collect_external_signals import (
    normalize_oanda_signal,
    parse_jsonish_list,
    polymarket_signal_from_probability,
    polymarket_yes_probability,
)


def test_polymarket_yes_probability_reads_yes_outcome_price() -> None:
    market = {
        "outcomes": '["No", "Yes"]',
        "outcomePrices": '["0.38", "0.62"]',
    }

    assert polymarket_yes_probability(market) == 0.62


def test_polymarket_signal_uses_threshold_direction() -> None:
    signal = polymarket_signal_from_probability(
        {
            "instrument": "EUR_USD",
            "yes_direction": "bearish",
            "no_direction": "bullish",
            "threshold": 0.58,
            "reason": "fed",
        },
        {"question": "Fed decision"},
        0.62,
        "2026-05-09T00:00:00Z",
    )

    assert signal is not None
    assert signal["instrument"] == "EUR_USD"
    assert signal["direction"] == "bearish"
    assert signal["source"] == "polymarket"


def test_normalize_oanda_signal_maps_symbol_direction_and_quality() -> None:
    signal = normalize_oanda_signal(
        {
            "symbol": "USD/JPY",
            "target_price": "154.20",
            "current_price": "155.00",
            "quality": "72",
            "pattern": "Key level",
            "timestamp": "2026-05-09T00:00:00Z",
        },
        {"source": "oanda_autochartist"},
        "2026-05-09T01:00:00Z",
    )

    assert signal is not None
    assert signal["instrument"] == "USD_JPY"
    assert signal["direction"] == "bearish"
    assert signal["confidence"] == 0.72
    assert signal["pattern"] == "Key level"


def test_parse_jsonish_list_rejects_invalid_json() -> None:
    assert parse_jsonish_list("not json") == []
