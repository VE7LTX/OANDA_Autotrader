"""
Streaming metrics aggregator.

Purpose:
- Track stream health (reconnects, errors) and throughput.
- Provide a quick snapshot for monitoring or logging.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import time


@dataclass
class StreamMetricsSnapshot:
    messages_total: int
    messages_per_sec: float
    reconnect_waits: int
    errors: int
    last_error: str | None
    last_message_ts: float | None
    last_error_ts: float | None
    last_reconnect_ts: float | None
    latency_last_ms: float | None
    latency_p95_ms: float | None
    latency_mean_ms: float | None


@dataclass
class StreamLatencySample:
    """
    Single stream latency sample (ms).
    """

    raw_ms: float
    milliseconds: float
    backlog: bool
    skew_ms: float | None
    outlier: bool
    timestamp: float


class StreamMetrics:
    """
    In-memory stream metrics for a single stream.
    """

    def __init__(self, *, window_seconds: int = 10) -> None:
        self._window_seconds = window_seconds
        self._message_ts: deque[float] = deque()
        self._latency_samples: deque[StreamLatencySample] = deque()
        self.messages_total = 0
        self.reconnect_waits = 0
        self.errors = 0
        self.last_error: str | None = None
        self.last_message_ts: float | None = None
        self.last_error_ts: float | None = None
        self.last_reconnect_ts: float | None = None
        self.last_latency_ms: float | None = None
        self.last_latency_raw_ms: float | None = None
        self.last_skew_ms: float | None = None
        self.last_backlog: bool | None = None

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
            self.last_reconnect_ts = event.get("received_ts", time.time())
            return
        if event_type == "stream_error":
            self.errors += 1
            self.last_error = event.get("error")
            self.last_error_ts = event.get("received_ts", time.time())

    def _trim(self, now: float) -> None:
        window_start = now - self._window_seconds
        while self._message_ts and self._message_ts[0] < window_start:
            self._message_ts.popleft()
        while self._latency_samples and self._latency_samples[0].timestamp < window_start:
            self._latency_samples.popleft()

    def messages_per_second(self) -> float:
        now = time.time()
        self._trim(now)
        return len(self._message_ts) / max(self._window_seconds, 1)

    def record_latency(self, server_time: str | None, received_ts: float) -> None:
        if not server_time:
            return
        server_ts = self._parse_timestamp(server_time)
        if server_ts is None:
            return
        raw_ms = (received_ts - server_ts) * 1000.0
        latency_ms, skew_ms, backlog, outlier = self._normalize_latency(raw_ms)
        self.last_latency_raw_ms = raw_ms
        self.last_latency_ms = latency_ms
        self.last_skew_ms = skew_ms
        self.last_backlog = backlog
        self._latency_samples.append(
            StreamLatencySample(
                raw_ms=raw_ms,
                milliseconds=latency_ms,
                backlog=backlog,
                skew_ms=skew_ms,
                outlier=outlier,
                timestamp=received_ts,
            )
        )
        self._trim(received_ts)

    def latency_stats(self) -> tuple[float | None, float | None, float | None]:
        values = [s.milliseconds for s in self._latency_samples if not s.outlier]
        if not values:
            return None, None, None
        values = sorted(values)
        mean = sum(values) / len(values)
        p95_index = max(0, int(round(0.95 * (len(values) - 1))))
        return self.last_latency_ms, values[p95_index], mean

    @staticmethod
    def _normalize_latency(raw_ms: float) -> tuple[float, float | None, bool, bool]:
        # Treat slight negative values as clock skew; clamp to 0 for stats.
        skew_ms = None
        backlog = False
        outlier = False
        if raw_ms < -250.0:
            outlier = True
        elif raw_ms < 0.0:
            skew_ms = abs(raw_ms)
            raw_ms = 0.0
        if raw_ms > 2000.0:
            backlog = True
        if raw_ms > 10000.0:
            outlier = True
        return raw_ms, skew_ms, backlog, outlier

    @staticmethod
    def _parse_timestamp(value: str) -> float | None:
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1]
        if "." in raw:
            head, frac = raw.split(".", 1)
            frac = frac[:6].ljust(6, "0")
            raw = f"{head}.{frac}"
        try:
            dt = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            return None

    def snapshot(self) -> StreamMetricsSnapshot:
        latency_last, latency_p95, latency_mean = self.latency_stats()
        return StreamMetricsSnapshot(
            messages_total=self.messages_total,
            messages_per_sec=self.messages_per_second(),
            reconnect_waits=self.reconnect_waits,
            errors=self.errors,
            last_error=self.last_error,
            last_message_ts=self.last_message_ts,
            last_error_ts=self.last_error_ts,
            last_reconnect_ts=self.last_reconnect_ts,
            latency_last_ms=latency_last,
            latency_p95_ms=latency_p95,
            latency_mean_ms=latency_mean,
        )
