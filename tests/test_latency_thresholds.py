import json
from pathlib import Path

from oanda_autotrader.trade_latency_gate import load_thresholds


def test_load_thresholds_from_file(tmp_path: Path) -> None:
    payload = {
        "skew_outlier_ms": 1000,
        "outlier_high_ms": 10000,
        "backlog_warn_ms": 200,
        "backlog_block_ms": 400,
        "consecutive_backlog_to_block": 3,
        "consecutive_good_to_unblock": 10,
        "min_samples": 60,
    }
    path = tmp_path / "latency_thresholds_live_USD_CAD.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    cfg, meta = load_thresholds("live", "USD_CAD", base_dir=str(tmp_path))
    assert meta["source"] == "file"
    assert cfg.backlog_warn_ms == 200
    assert cfg.backlog_block_ms == 400


def test_load_thresholds_missing_uses_defaults(tmp_path: Path) -> None:
    cfg, meta = load_thresholds("live", "USD_CAD", base_dir=str(tmp_path))
    assert meta["source"] == "defaults"
    assert cfg.backlog_warn_ms == 1500.0
