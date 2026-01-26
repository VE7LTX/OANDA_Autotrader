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
