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
