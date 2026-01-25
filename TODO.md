# TODO

## P0 Reliability
- Add async monitoring loop with rolling latency stats.
- Add per-stream reconnect metrics (count, last error, last success).

## P1 Models
- Add typed models for REST responses (Account, Position, Trade, etc.).
- Expand stream parsing for PRICE/TRANSACTION fields.
- Add validation for required fields (id, accountID, instrument).

## P1 Testing
- Add unit tests for config parsing, validation, and stream parsing.
- Add integration tests for practice/live account checks.
- Add a smoke test for streaming reconnection.

## P2 Ops
- Add CLI wrappers for health checks and streaming.
- Add structured log output format (JSONL).
- Add a rotating file handler for long-running services.
