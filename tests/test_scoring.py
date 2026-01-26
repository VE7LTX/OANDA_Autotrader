from __future__ import annotations

import json
from pathlib import Path

from scripts.score_predictions import score_once


def write_candle(path: Path, ts: str, close: float) -> None:
    payload = {"time": ts, "mid": {"c": str(close)}}
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def test_score_once_aligns_steps(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    candle_path = data_dir / "usd_cad_candles_20260101.jsonl"
    pred_path = tmp_path / "predictions_latest.jsonl"
    score_path = tmp_path / "prediction_scores.jsonl"

    pred = {
        "ts": "2026-01-01T00:00:00Z",
        "interval_secs": 5,
        "horizon": [
            {"step": 1, "mean": 1.0, "low": 0.9, "high": 1.1},
            {"step": 2, "mean": 1.0, "low": 0.95, "high": 1.05},
        ],
    }
    pred_path.write_text(json.dumps(pred) + "\n", encoding="utf-8")

    write_candle(candle_path, "2026-01-01T00:00:05.000000000Z", 1.02)
    write_candle(candle_path, "2026-01-01T00:00:10.000000000Z", 0.94)

    scored_ts = set()
    score_once(str(pred_path), str(score_path), str(data_dir), scored_ts)
    rows = score_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1
    payload = json.loads(rows[0])
    assert payload["coverage"] == 0.5
    assert payload["results"][0]["hit"] is True
    assert payload["results"][1]["hit"] is False
    buckets = {item["label"]: item for item in payload["buckets"]}
    assert buckets["1-3"]["resolved"] == 2


def test_score_once_handles_bad_timestamp(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pred_path = tmp_path / "predictions_latest.jsonl"
    score_path = tmp_path / "prediction_scores.jsonl"

    pred = {
        "ts": "not-a-timestamp",
        "interval_secs": 5,
        "horizon": [{"step": 1, "mean": 1.0, "low": 0.9, "high": 1.1}],
    }
    pred_path.write_text(json.dumps(pred) + "\n", encoding="utf-8")

    scored_ts = set()
    score_once(str(pred_path), str(score_path), str(data_dir), scored_ts)
    rows = score_path.read_text(encoding="utf-8").strip().splitlines()
    payload = json.loads(rows[0])
    assert payload["coverage"] is None
