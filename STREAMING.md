# Streaming Notes

OANDA streaming is HTTP chunked streaming, not WebSocket. The client keeps a
long-lived GET request open and receives newline-delimited JSON messages.

## Stream Endpoints
- Pricing: `/v3/accounts/{accountID}/pricing/stream`
- Transactions: `/v3/accounts/{accountID}/transactions/stream`

## Reconnect Strategy
- Exponential backoff with jitter (default base 0.5s, max 15s).
- `max_retries=None` means reconnect forever.
- `reconnect=False` disables auto-reconnect and surfaces errors.

## Env Settings
- `OANDA_STREAM_RECONNECT` (true/false)
- `OANDA_STREAM_MAX_RETRIES` (blank for unlimited)
- `OANDA_STREAM_BACKOFF_BASE_SECONDS`
- `OANDA_STREAM_BACKOFF_MAX_SECONDS`
- `OANDA_STREAM_TIMEOUT_SECONDS` (0 = no total timeout)

## Parsed Message Types
- PRICE: pricing updates (instrument, time, bids/asks).
- TRANSACTION: transaction events (order fills, account changes).
- HEARTBEAT: keep-alive signals.
- UNKNOWN: anything else is preserved as a raw payload.

## Error Handling Notes
- Malformed JSON lines are skipped to keep the stream alive.
- Network errors trigger reconnect if enabled.
- For debugging, enable `OANDA_DEBUG_LOGGING` to see request logs.

## Next Ideas
- Add structured logging on reconnects and stream errors.
- Record stream latency by comparing server timestamps with local clock.
- Add per-stream metrics (messages/sec, error counts).
