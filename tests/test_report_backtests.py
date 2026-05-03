from __future__ import annotations

import json
from pathlib import Path


def test_report_input_shape(tmp_path) -> None:
    payload = {
        "instrument": "USD_CAD",
        "granularity": "M5",
        "replay": {
            "summary": {
                "trade_count": 10,
                "win_rate": 0.6,
                "gross_pnl": 1.0,
                "net_pnl": 0.8,
                "expectancy": 0.08,
                "max_drawdown": -0.2,
            }
        },
    }
    path = tmp_path / "backtest_test.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["replay"]["summary"]["trade_count"] == 10
