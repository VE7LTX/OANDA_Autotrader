import os
from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture(autouse=True)
def clear_env():
    keys = [
        "DEMO_OANDA_API_KEY",
        "LIVE_OANDA_API_KEY",
        "OANDA_API_BASE_PRACTICE",
        "OANDA_API_BASE_LIVE",
        "OANDA_STREAM_BASE_PRACTICE",
        "OANDA_STREAM_BASE_LIVE",
        "OANDA_STREAM_RECONNECT",
        "OANDA_STREAM_MAX_RETRIES",
        "OANDA_STREAM_BACKOFF_BASE_SECONDS",
        "OANDA_STREAM_BACKOFF_MAX_SECONDS",
        "OANDA_REQUESTS_PER_SECOND",
        "OANDA_REQUEST_TIMEOUT_SECONDS",
    ]
    original = {key: os.getenv(key) for key in keys}
    for key in keys:
        if key in os.environ:
            del os.environ[key]
    yield
    for key, value in original.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
