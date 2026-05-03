"""
Simple rate limiters for request throughput control.

Purpose:
- Keep request rate under OANDA's recommended limits.
- Provide lightweight control without external dependencies.
"""

from __future__ import annotations

from collections import deque
import asyncio
import time


class RateLimiter:
    """
    Synchronous token bucket style limiter (per-second window).
    """

    def __init__(self, max_per_second: int) -> None:
        if max_per_second <= 0:
            raise ValueError("max_per_second must be > 0")
        self._max = max_per_second
        self._timestamps: deque[float] = deque()

    def wait(self) -> None:
        now = time.perf_counter()
        window_start = now - 1.0
        while self._timestamps and self._timestamps[0] < window_start:
            self._timestamps.popleft()
        if len(self._timestamps) >= self._max:
            sleep_for = 1.0 - (now - self._timestamps[0])
            if sleep_for > 0:
                time.sleep(sleep_for)
        self._timestamps.append(time.perf_counter())


class AsyncRateLimiter:
    """
    Async token bucket style limiter (per-second window).
    """

    def __init__(self, max_per_second: int) -> None:
        if max_per_second <= 0:
            raise ValueError("max_per_second must be > 0")
        self._max = max_per_second
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.perf_counter()
            window_start = now - 1.0
            while self._timestamps and self._timestamps[0] < window_start:
                self._timestamps.popleft()
            if len(self._timestamps) >= self._max:
                sleep_for = 1.0 - (now - self._timestamps[0])
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
            self._timestamps.append(time.perf_counter())
