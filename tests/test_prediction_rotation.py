from __future__ import annotations

import json
from pathlib import Path

from scripts.train_autoencoder_loop import write_json_latest


def test_write_json_latest_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "predictions_latest.jsonl"
    write_json_latest(str(path), {"run": 1})
    write_json_latest(str(path), {"run": 2})
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["run"] == 2


def test_archive_path_format(tmp_path: Path) -> None:
    archive_dir = tmp_path / "predictions"
    archive_dir.mkdir()
    payload = {"run": 1}
    archive_path = archive_dir / "predictions_20260101_0101.jsonl"
    archive_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    assert archive_path.exists()
