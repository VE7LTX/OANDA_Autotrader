from __future__ import annotations

import json

from scripts.run_bot_monitor import classify_status, format_block, format_snapshot_summary, read_json, read_last_jsonl


def test_read_jsonl_last_line(tmp_path) -> None:
    path = tmp_path / "bot_audit.jsonl"
    path.write_text('{"a": 1}\n{"b": 2}\n', encoding="utf-8")
    assert read_last_jsonl(path) == {"b": 2}


def test_read_json(tmp_path) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"x": 1}), encoding="utf-8")
    assert read_json(path) == {"x": 1}


def test_format_block_returns_pretty_json() -> None:
    output = format_block({"a": 1})
    assert '"a": 1' in output


def test_read_helpers_support_custom_paths(tmp_path) -> None:
    audit = tmp_path / "live_audit.jsonl"
    state = tmp_path / "live_state.json"
    audit.write_text('{"instrument":"GBP_USD"}\n', encoding="utf-8")
    state.write_text(json.dumps({"current_position": {"side": "short"}}), encoding="utf-8")
    assert read_last_jsonl(audit)["instrument"] == "GBP_USD"
    assert read_json(state)["current_position"]["side"] == "short"


def test_classify_status_distinguishes_cooldown_and_risk() -> None:
    assert classify_status({"blocked": ["cooldown_active"]}, ["cooldown_active"]) == "COOLDOWN"
    assert classify_status({"blocked": ["regime_filter_blocked"]}, ["regime_filter_blocked"]) == "RISK BLOCKED"
    assert classify_status({"error": "boom"}, []) == "ERROR"
    assert classify_status({}, []) == "READY"


def test_format_snapshot_summary_includes_pnl() -> None:
    summary = format_snapshot_summary(
        {
            "nav": 10050.0,
            "balance": 10000.0,
            "open_trade_count": 2,
            "positions_by_instrument": {"GBP_USD": -100, "EUR_USD": 100},
            "unrealized_pnl": 50.0,
            "realized_pnl_day": 12.5,
        }
    )
    assert "Unrealized: 50.0" in summary
    assert "Realized: 12.5" in summary
