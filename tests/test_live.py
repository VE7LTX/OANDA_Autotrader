import os
import subprocess
import sys

import pytest


pytestmark = pytest.mark.live


def require_live() -> None:
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("RUN_LIVE_TESTS=1 required for live integration tests")


def test_run_checks_script() -> None:
    require_live()
    result = subprocess.run(
        [sys.executable, "scripts/run_checks.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "accounts" in result.stdout


def test_run_instrument_checks_script() -> None:
    require_live()
    result = subprocess.run(
        [sys.executable, "scripts/run_instrument_checks.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "instrument" in result.stdout
