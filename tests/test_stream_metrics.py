from datetime import datetime, timezone

from oanda_autotrader.stream_metrics import StreamMetrics


def test_stream_metrics_counts_messages() -> None:
    metrics = StreamMetrics(window_seconds=10)
    metrics.on_event({"event": "stream_message", "received_ts": 1.0})
    metrics.on_event({"event": "stream_message", "received_ts": 2.0})
    snapshot = metrics.snapshot()
    assert snapshot.messages_total == 2


def test_stream_metrics_errors_and_reconnects() -> None:
    metrics = StreamMetrics(window_seconds=10)
    metrics.on_event({"event": "stream_error", "error": "boom", "received_ts": 3.0})
    metrics.on_event({"event": "stream_reconnect_wait", "delay_seconds": 1.0, "received_ts": 4.0})
    snapshot = metrics.snapshot()
    assert snapshot.errors == 1
    assert snapshot.reconnect_waits == 1
    assert snapshot.last_error == "boom"


def test_stream_metrics_latency_parsing() -> None:
    metrics = StreamMetrics(window_seconds=10)
    base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp()
    metrics.record_latency("2026-01-01T00:00:00.123456789Z", base + 0.5)
    last, p95, mean = metrics.latency_stats()
    assert last is not None
    assert p95 is not None
    assert mean is not None


def test_stream_metrics_negative_skew_clamped() -> None:
    metrics = StreamMetrics(window_seconds=10)
    base = datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc).timestamp()
    metrics.record_latency("2026-01-01T00:00:10.000000000Z", base - 0.1)
    assert metrics.last_latency_ms == 0.0
    assert metrics.last_skew_ms is not None


def test_stream_metrics_backlog_flag() -> None:
    metrics = StreamMetrics(window_seconds=10)
    base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp()
    metrics.record_latency("2026-01-01T00:00:00.000000000Z", base + 5.0)
    assert metrics.last_backlog is True
