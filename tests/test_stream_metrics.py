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
    metrics.record_latency("2026-01-01T00:00:00.123456789Z", 10.0)
    last, p95, mean = metrics.latency_stats()
    assert last is not None
    assert p95 is not None
    assert mean is not None
