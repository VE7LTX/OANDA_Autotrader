import time

import pytest

from oanda_autotrader.rate_limit import AsyncRateLimiter, RateLimiter


def test_rate_limiter_rejects_invalid_max() -> None:
    with pytest.raises(ValueError):
        RateLimiter(0)
    with pytest.raises(ValueError):
        AsyncRateLimiter(0)


def test_rate_limiter_wait_delays(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = RateLimiter(1)
    times = [1000.0, 1000.0, 1000.1, 1001.2]
    monkeypatch.setattr(time, "perf_counter", lambda: times.pop(0))
    called = []
    monkeypatch.setattr(time, "sleep", lambda s: called.append(s))
    limiter.wait()
    limiter.wait()
    assert called, "Expected sleep to be called for rate limiting"
