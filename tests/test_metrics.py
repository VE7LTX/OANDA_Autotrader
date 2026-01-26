from __future__ import annotations

import time

from oanda_autotrader.metrics import LatencyTracker


def test_latency_tracker_stats() -> None:
    tracker = LatencyTracker()
    tracker.add("practice", 100.0)
    tracker.add("practice", 200.0)
    stats = tracker.stats("practice")
    assert stats.count == 2
    assert stats.min_ms == 100.0
    assert stats.max_ms == 200.0
    assert stats.mean_ms == 150.0


def test_latency_tracker_names() -> None:
    tracker = LatencyTracker()
    tracker.add("practice", 50.0)
    tracker.add("live", 60.0)
    assert set(tracker.all_names()) == {"live", "practice"}
