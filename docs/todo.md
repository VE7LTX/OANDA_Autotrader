# TODO

## P0 Core Pipeline (must be solid before new features)
- Ensure instrument streaming runs continuously (capture + dashboard stays alive).
- Ensure prediction loop updates `data/predictions_latest.jsonl` continuously.
- Ensure scoring loop resolves steps after enough future candles (coverage/MAE).
- Add stream latency estimation (server time vs local receive time).
- Add per-stream reconnect metrics (count, last error, last success).
- Add async monitoring loop with rolling latency stats.

## P1 Data Contracts and Validation (prevents redo)
- Add typed models for REST responses (Account, Position, Trade, etc.).
- Expand stream parsing for PRICE/TRANSACTION fields.
- Add validation for required fields (id, accountID, instrument).
- Add feature scaling audits for autoencoder inputs (min/max tracking).

## P1 Testing (targeted, low-redo)
- Expand live tests to cover dashboard data sources (predictions_latest, scores).
- Add smoke test for streaming reconnection (live-only).
- Add live scoring resolution test (wait for horizon to resolve).

## P2 Ops (polish after core is stable)
- Add CLI wrappers for health checks and streaming.
- Add structured log output format (JSONL).
- Add a rotating file handler for long-running services.

## P0 Practice Trading MVP (after core pipeline is stable)
- Build a dedicated trading loop/service (not tied to pygame lifecycle).
- Implement market-only entries with mandatory SL/TP bracket.
- Add risk engine:
  - 0.25% NAV risk per trade
  - max 1 open position per instrument, max 2 total
  - max 3 trades/hour
  - cooldown 60–180s after close
  - daily loss limit 1.0% NAV -> kill-switch until next day
- Add execution hygiene filters:
  - stale data guard (candles/predictions freshness)
  - spread filter (skip if spread > 2x median recent spread)
  - slippage guard (flag > X pips)
- Add signal logic (MVP):
  - band excursion + mean reversion to predicted mean
  - simple trend/volatility filter to avoid strong trends
- Add state machine:
  - IDLE → SIGNAL → SUBMIT → FILLED → MANAGE → EXIT → COOLDOWN
- Add dry-run mode (log decisions, no orders).
- Add metrics/logs:
  - entry/exit reason codes, slippage, spread, P&L per trade
- Add kill switches:
  - env flag to disable trading
  - STOP file to halt immediately
