# Streaming Notes

OANDA streaming is HTTP chunked streaming, not WebSocket. The client keeps a
long-lived GET request open and receives newline-delimited JSON messages.

## Client Summary
- Client: `src/oanda_autotrader/streaming.py` (`OandaStreamClient`)
- Transport: `aiohttp` with an async generator interface
- Output: typed `StreamMessage` wrappers in `src/oanda_autotrader/models.py`

## Stream Endpoints
- Pricing: `/v3/accounts/{accountID}/pricing/stream`
- Transactions: `/v3/accounts/{accountID}/transactions/stream`

## Reconnect Strategy
- Exponential backoff with jitter (default base 0.5s, max 15s).
- `max_retries=None` means reconnect forever.
- `reconnect=False` disables auto-reconnect and surfaces errors.
- `on_event` hooks receive reconnect delays and error events for metrics.

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

## Metrics
- `StreamMetrics` aggregates messages/sec, errors, reconnect waits.
- Hook it into streaming via `build_stream_client(config, on_event=metrics.on_event)`.
- `StreamMetricsSnapshot` provides a single record for dashboards/logging.

## Next Ideas
- Add structured logging on reconnects and stream errors.
- Record stream latency by comparing server timestamps with local clock.
- Add per-stream metrics (messages/sec, error counts).
