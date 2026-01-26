"""
Streaming metrics aggregator.

Purpose:
- Track stream health (reconnects, errors) and throughput.
- Provide a quick snapshot for monitoring or logging.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import time


@dataclass
class StreamMetricsSnapshot:
    messages_total: int
    messages_per_sec: float
    reconnect_waits: int
    errors: int
    last_error: str | None
    last_message_ts: float | None


class StreamMetrics:
    """
    In-memory stream metrics for a single stream.
    """

    def __init__(self, *, window_seconds: int = 10) -> None:
        self._window_seconds = window_seconds
        self._message_ts: deque[float] = deque()
        self.messages_total = 0
        self.reconnect_waits = 0
        self.errors = 0
        self.last_error: str | None = None
        self.last_message_ts: float | None = None

    def on_event(self, event: dict) -> None:
        event_type = event.get("event")
        if event_type == "stream_message":
            ts = event.get("received_ts", time.time())
            self.messages_total += 1
            self.last_message_ts = ts
            self._message_ts.append(ts)
            self._trim(ts)
            return
        if event_type == "stream_reconnect_wait":
            self.reconnect_waits += 1
            return
        if event_type == "stream_error":
            self.errors += 1
            self.last_error = event.get("error")

    def _trim(self, now: float) -> None:
        window_start = now - self._window_seconds
        while self._message_ts and self._message_ts[0] < window_start:
            self._message_ts.popleft()

    def messages_per_second(self) -> float:
        now = time.time()
        self._trim(now)
        return len(self._message_ts) / max(self._window_seconds, 1)

    def snapshot(self) -> StreamMetricsSnapshot:
        return StreamMetricsSnapshot(
            messages_total=self.messages_total,
            messages_per_sec=self.messages_per_second(),
            reconnect_waits=self.reconnect_waits,
            errors=self.errors,
            last_error=self.last_error,
            last_message_ts=self.last_message_ts,
        )
