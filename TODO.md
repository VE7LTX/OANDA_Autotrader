# TODO

## P0 Reliability
- Add async monitoring loop with rolling latency stats.
- Add per-stream reconnect metrics (count, last error, last success).
- Add stream latency estimation (server time vs local receive time).

## P1 Models
- Add typed models for REST responses (Account, Position, Trade, etc.).
- Expand stream parsing for PRICE/TRANSACTION fields.
- Add validation for required fields (id, accountID, instrument).
- Add feature scaling audits for autoencoder inputs (min/max tracking).

## P1 Testing
- Expand live tests to cover dashboard data sources.
- Add smoke test for streaming reconnection (live-only).

## P2 Ops
- Add CLI wrappers for health checks and streaming.
- Add structured log output format (JSONL).
- Add a rotating file handler for long-running services.
