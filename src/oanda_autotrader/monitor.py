"""
Monitoring helpers for response time tracking.

Purpose:
- Provide simple latency measurement hooks for practice/live checks.
- Keep monitoring logic separate from endpoint definitions.
"""

from __future__ import annotations

import time

from .app import load_account_client
from .metrics import LatencyTracker


def measure_account_latency(
    accounts_path: str,
    group_name: str,
    account_name: str,
    *,
    label: str | None = None,
) -> tuple[dict[str, object], float]:
    """
    Measure latency for GET /v3/accounts and return response + timing.
    """

    client = load_account_client(accounts_path, group_name, account_name)
    start = time.perf_counter()
    response = client.list_accounts()
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return response, elapsed_ms


def sample_practice_live_latency(
    accounts_path: str,
    *,
    demo_account_name: str = "Primary",
    live_account_name: str = "Primary",
) -> LatencyTracker:
    """
    Sample practice + live endpoints once each and return a tracker.
    """

    tracker = LatencyTracker()
    _, demo_ms = measure_account_latency(accounts_path, "demo", demo_account_name)
    tracker.add("practice", demo_ms)
    _, live_ms = measure_account_latency(accounts_path, "live", live_account_name)
    tracker.add("live", live_ms)
    return tracker
