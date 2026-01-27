"""
Async monitoring loop for rolling system stats.

Outputs JSONL snapshots for dashboards and postmortem analysis.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict

from .metrics import LatencyTracker
from .monitor import sample_practice_live_latency
from .stream_metrics import StreamMetrics
from .trade_latency_gate import TradeLatencyGate
from .retrain_gate import evaluate_retrain_gate


def _write_jsonl(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


async def monitor_loop(
    *,
    accounts_path: str,
    interval_seconds: float,
    output_path: str,
    stream_metrics: StreamMetrics,
    trade_gate: TradeLatencyGate | None = None,
    retrain_gate_kwargs: dict | None = None,
) -> None:
    tracker = LatencyTracker()
    while True:
        # REST latency snapshot (practice/live).
        sample = await _to_thread(sample_practice_live_latency, accounts_path)
        for item in sample.samples():
            tracker.add(item.name, item.milliseconds)

        rest_stats = {}
        for name in tracker.all_names():
            stats = tracker.stats(name)
            rest_stats[name] = asdict(stats)

        stream_snapshot = stream_metrics.snapshot()
        gate_snapshot = trade_gate.snapshot() if trade_gate else None
        retrain_snapshot = None
        if retrain_gate_kwargs:
            try:
                decision = evaluate_retrain_gate(**retrain_gate_kwargs)
                retrain_snapshot = {
                    "allow": decision.allow,
                    "reason": decision.reason,
                    "coverage": decision.coverage,
                    "mae": decision.mae,
                    "mae_threshold": decision.mae_threshold,
                    "window_n": decision.window_n,
                    "fields_used": decision.fields_used,
                    "blocked": decision.blocked,
                    "stale": decision.stale,
                }
            except Exception:
                retrain_snapshot = {"error": "retrain_gate_failed"}

        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rest": rest_stats,
            "stream": asdict(stream_snapshot),
            "trade_gate": gate_snapshot,
            "retrain_gate": retrain_snapshot,
        }
        _write_jsonl(output_path, payload)
        await _sleep(interval_seconds)


async def _to_thread(fn, *args, **kwargs):
    import asyncio

    return await asyncio.to_thread(fn, *args, **kwargs)


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
