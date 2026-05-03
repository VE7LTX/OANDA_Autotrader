import json
import os
from pathlib import Path

import pytest

from oanda_autotrader.monitoring import _write_jsonl


def test_write_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "monitor.jsonl"
    payload = {"ts": "2026-01-01T00:00:00Z", "ok": True}
    _write_jsonl(str(path), payload)
    data = json.loads(path.read_text(encoding="utf-8").strip())
    assert data["ok"] is True
