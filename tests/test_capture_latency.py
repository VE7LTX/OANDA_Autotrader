import asyncio
import json
from types import SimpleNamespace

import pytest

import scripts.capture_latency as capture_latency


class DummyStream:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def stream_pricing(self, account_id, instruments):
        yield {"type": "PRICE", "time": "2026-01-01T00:00:00Z"}


def test_capture_practice_maps_to_demo_and_logs_mode(tmp_path, monkeypatch):
    seen = {}

    def fake_select_account(groups, group_name, account_name):
        seen["group_name"] = group_name
        return object(), SimpleNamespace(account_id="123-456")

    monkeypatch.setattr(capture_latency, "load_account_groups", lambda *_: object())
    monkeypatch.setattr(capture_latency, "select_account", fake_select_account)
    monkeypatch.setattr(capture_latency, "resolve_account_credentials", lambda *_: {"token": "x"})
    monkeypatch.setattr(capture_latency, "build_stream_client", lambda *_: DummyStream())

    out_path = tmp_path / "stream_latency.jsonl"
    args = SimpleNamespace(
        mode="practice",
        account="Primary",
        instrument="USD_CAD",
        seconds=0,
        output=str(out_path),
        log_interval=0.0,
        pid_file=None,
    )

    asyncio.run(capture_latency.run_capture(args))

    assert seen["group_name"] == "demo"
    payload = json.loads(out_path.read_text(encoding="utf-8").splitlines()[-1])
    assert payload["mode"] == "practice"
    assert payload["instrument"] == "USD_CAD"
