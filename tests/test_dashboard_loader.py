from __future__ import annotations

import json
from pathlib import Path

from scripts.dashboard_pygame import load_latest_prediction


def test_load_latest_prediction_skips_stale(tmp_path: Path) -> None:
    path = tmp_path / "predictions.jsonl"
    stale = {"ts": "2026-01-01T00:00:00Z", "foo": "bar"}
    valid = {
        "ts": "2026-01-01T00:00:10Z",
        "horizon_secs": 60,
        "interval_secs": 5,
        "horizon": [{"step": 1, "mean": 1.0, "low": 0.9, "high": 1.1}],
    }
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(stale) + "\n")
        handle.write(json.dumps(valid) + "\n")
    loaded = load_latest_prediction(str(path))
    assert loaded is not None
    assert loaded["horizon_secs"] == 60


def test_load_latest_prediction_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.jsonl"
    assert load_latest_prediction(str(path)) is None
