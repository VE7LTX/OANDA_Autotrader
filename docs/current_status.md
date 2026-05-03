# Current Status

## What Is Working

- package layout under `src/oanda_autotrader`
- local example/bootstrap files
- practice-account authentication
- practice dry-run bot cycle
- stale-data health gate
- practice-only execution engine
- persistent bot state and failure backoff
- position-aware strategy behavior
- explicit close actions
- local audit logging

## What Is Not Implemented Yet

- spread-aware trade gating
- advanced exit management
- performance scoring from bot audit logs
- portfolio or multi-instrument orchestration
- external AI oversight in the bot loop
- real-account execution gate

## Current Local Files To Watch

- `data/bot_audit.jsonl`
- `data/bot_state.json`
- `data/ai_trade_audit.jsonl`

## Practical Test Sequence

1. Run one dry-run bot cycle.
2. Confirm health gate result and latest action.
3. If data is fresh and the bot is not blocked, observe the proposed order.
4. Run repeated dry-run cycles before enabling `--submit`.
5. Use practice execution only after reviewing audit output.

## Remaining Action Items

- add summary stats from bot audit logs
- add spread or quote freshness checks
- add more nuanced exit logic
- build AI oversight only after deterministic behavior is stable
