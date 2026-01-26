# Config Reference

## How Config Loads
1) `accounts.yaml` defines account groups and account IDs.
2) `.env` provides tokens and optional overrides.
3) Environment variables override `.env` if already set.

## Required Tokens
- `DEMO_OANDA_API_KEY`
- `LIVE_OANDA_API_KEY`

## Optional IDs (for future overrides)
- `DEMO_OANDA_ACCOUNT_ID`
- `LIVE_OANDA_ACCOUNT_ID`

## REST Base URLs
- `OANDA_API_BASE_PRACTICE` (default: `https://api-fxpractice.oanda.com`)
- `OANDA_API_BASE_LIVE` (default: `https://api-fxtrade.oanda.com`)

## Streaming Base URLs
- `OANDA_STREAM_BASE_PRACTICE` (default: `https://stream-fxpractice.oanda.com`)
- `OANDA_STREAM_BASE_LIVE` (default: `https://stream-fxtrade.oanda.com`)

## Performance & Reliability
- `OANDA_REQUEST_TIMEOUT_SECONDS` (default: 30)
- `OANDA_REQUESTS_PER_SECOND` (default: 100)
- `OANDA_DEBUG_LOGGING` (default: false)
- `OANDA_STREAM_TIMEOUT_SECONDS` (default: 0 = no total timeout)
- `OANDA_STREAM_RECONNECT` (default: true)
- `OANDA_STREAM_MAX_RETRIES` (default: unlimited if blank)
- `OANDA_STREAM_BACKOFF_BASE_SECONDS` (default: 0.5)
- `OANDA_STREAM_BACKOFF_MAX_SECONDS` (default: 15.0)

## Recommended Defaults
- Keep `OANDA_REQUESTS_PER_SECOND` at 100 to match OANDA guidance.
- Use `OANDA_STREAM_RECONNECT=true` for production feeds.
- Set `OANDA_DEBUG_LOGGING=true` only when diagnosing issues.

## Logging
- Use `setup_logging(json_output=True)` for JSONL logs.

## Data Capture (USD_CAD)
- `OANDA_CAPTURE_GROUP` (default: live)
- `OANDA_CAPTURE_ACCOUNT` (default: Primary)
- `OANDA_CAPTURE_INSTRUMENT` (default: USD_CAD)
- `OANDA_CAPTURE_DIR` (default: data)
- `OANDA_CAPTURE_ROTATE_MINUTES` (default: 60)
- `OANDA_CAPTURE_CANDLE_INTERVAL_SECONDS` (default: 300)
- `OANDA_CAPTURE_GRANULARITY` (default: S5)
- `OANDA_CAPTURE_PRICE` (default: M)
- `OANDA_CAPTURE_COUNT` (default: 500)

## Dataset Builder
- `scripts/build_dataset.py` reads `data/usd_cad_candles_*.jsonl`.
- Outputs windows of normalized close prices for autoencoder training.

## Feature Builder
- `scripts/build_features.py` computes RSI, SMA/EMA, MACD, Bollinger Bands, ATR, ADX, Stochastic, OBV, VWAP, returns, volume.

## Autoencoder Status Feed
- Write JSONL status updates to `data/ae_status.jsonl` for dashboard display.
- Example line: `{"ts":"2026-01-26T00:45:00Z","epoch":5,"loss":0.0123}`
 - Dummy writer: `scripts/write_ae_status.py` appends a new status every 2s.

## Dashboard
- `OANDA_DASHBOARD_LATENCY_INTERVAL` (default: 5)
- `OANDA_DASHBOARD_HISTORY` (default: 120)
- `OANDA_DASHBOARD_INSTRUMENT` (default: USD_CAD)
- `OANDA_DASHBOARD_GROUP` (default: live)
- `OANDA_DASHBOARD_ACCOUNT` (default: Primary)
- `OANDA_DASHBOARD_SUMMARY_INTERVAL` (default: 10)
- `OANDA_DASHBOARD_CANDLE_INTERVAL` (default: 10)
- `OANDA_DASHBOARD_CANDLE_POINTS` (default: 120)
- `OANDA_DASHBOARD_AE_STATUS_PATH` (default: data/ae_status.jsonl)
- `OANDA_DASHBOARD_AE_STATUS_INTERVAL` (default: 5)
