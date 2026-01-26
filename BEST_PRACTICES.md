# Best Practices

## Scope
These notes combine OANDA guidance with practical handling in this repo:
- request pacing
- long-lived sessions
- account state synchronization
- streaming resilience
- monitoring + scoring discipline

## Connection Limits
- New connections: limit to ~2 per second to avoid excessive TCP/SSL setup.
- Requests on a persistent connection: limit to ~100 per second.
- Prefer long-lived sessions (requests.Session / aiohttp.ClientSession) to reuse TCP.
- If you need bursts, warm the pool first and ramp up gradually.

## Persistent Connections
- HTTP/1.1 keep-alive is enabled by default on compliant clients.
- Avoid setting the `Connection` header to values that disable keep-alive.
- For HTTP/1.0 clients, explicitly send `Connection: Keep-Alive`.

## Account State Sync Pattern
The recommended pattern is: **full snapshot once, then incremental updates**.

### Startup
1) Call **Account Details** to get a full snapshot (orders, trades, positions).
2) Store the returned `lastTransactionID` from the response.
3) Keep the snapshot in memory (or a fast store) for quick updates.

### Update Loop
1) Call **Poll Account Updates** with the most recent `lastTransactionID`.
2) Apply `AccountChanges` to your snapshot (add/remove/replace orders/trades/positions).
3) Replace price-sensitive fields using `AccountState`.
4) Save the new `lastTransactionID` for the next poll.

### Why This Matters
- `AccountChanges` are event-driven (less frequent).
- `AccountState` updates can be frequent (price-dependent).
- Keeping these separate preserves consistency while handling high-rate price changes.

## Reliability Tips
- Handle disconnects with exponential backoff and jitter.
- Log request latency and error rates separately for practice vs live.
- Fail fast on config errors (missing tokens, bad account IDs).
- Use timeouts and retries for idempotent requests only.

## Streaming Tips
- Treat the stream as an always-on pipe; reconnect with backoff on disconnect.
- HEARTBEAT events are normal; they confirm the stream is alive.
- Avoid doing heavy work on the stream loop; queue work to a worker thread/task.

## Forecasting and Scoring
- The forecast band is a short-horizon statistical envelope, not a guarantee.
- Scoring is delayed by definition; a prediction can be scored only after the
  future candles arrive.
- Use bucketed metrics (1-3, 4-8, 9-12 steps) to compare short vs longer horizons.
