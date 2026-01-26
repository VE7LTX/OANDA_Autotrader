# Testing Guide

## Philosophy
- Default test runs must be offline, deterministic, and fast.
- Live tests are opt-in and gated with `RUN_LIVE_TESTS=1`.
- Avoid tests that require pygame rendering, timing-sensitive streams, or real tokens.

## Quick Start
Install dev dependencies:
```bash
pip install -r requirements-dev.txt
```

Run unit tests (no network):
```bash
pytest
```

Run live tests (requires valid `.env` + accounts.yaml):
```bash
set RUN_LIVE_TESTS=1
pytest -m live
```

## What Gets Tested (Offline)
- Config parsing and environment resolution.
- Accounts/instruments endpoint path and params generation.
- Rate limiting behavior.
- Stream metrics aggregation.
- Prediction file rotation (single-line overwrite).
- Dashboard prediction loader schema filtering.
- Scoring alignment (timestamp parsing, hits, buckets, MAE).

## Live Tests (Opt-In)
- `scripts/run_checks.py` should return non-empty account/instrument counts.
- `scripts/run_instrument_checks.py` should return complete candles for default instruments.

## Forecast Scoring Reminder
Scoring requires future candles. The scorer will emit `coverage=None` until
new candles exist after the prediction timestamp.
