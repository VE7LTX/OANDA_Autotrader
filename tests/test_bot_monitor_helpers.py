from __future__ import annotations

import json

from scripts.run_bot_monitor import format_block, read_json, read_last_jsonl


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
