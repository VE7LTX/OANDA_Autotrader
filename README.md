# Oanda SDK / Autotrader Merge Workspace

This workspace is the active merge point between an older flat `Oanda_SDK`
prototype and the more structured `OANDA_Autotrader` package layout.

Current focus:
- practice-account trading only
- deterministic bot before external AI oversight
- strong audit logging and safety gates
- local monitoring so the bot can be observed while it runs

## Current State

Implemented:
- packaged code under `src/oanda_autotrader`
- account/instrument/order endpoint wrappers
- practice-only execution engine
- deterministic moving-average bot
- health gates for stale data, candle sufficiency, risk policy, and failure backoff
- JSONL audit logging
- persistent bot state
- example files for local setup

Current blocker history:
- practice auth is now working
- Sunday stale-data gating worked correctly before market reopen

## Editable Files

- `.env.example`
- `accounts.yaml.example`
- `decision.example.json`

If any sample files are deleted:

```bash
python scripts/bootstrap_example_files.py
```

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

2. Create local config:

```bash
copy .env.example .env
copy accounts.yaml.example accounts.yaml
```

3. Fill in real local values for:
- practice token
- practice account ID
- optional live values

Real secrets stay local. `.env`, `accounts.yaml`, and `data/` are gitignored.

## Main Entry Points

Practice bot dry-run:

```bash
python scripts/run_bot.py --group demo --account Primary --instrument USD_CAD --dry-run --iterations 1
```

Practice bot repeated polling:

```bash
python scripts/run_bot.py --group demo --account Primary --instrument USD_CAD --dry-run --iterations 10 --interval-seconds 60
```

Practice bot with explicit submission:

```bash
python scripts/run_bot.py --group demo --account Primary --instrument USD_CAD --submit --iterations 1
```

AI experiment runner:

```bash
python scripts/run_ai_experiment.py --group demo --account Primary --instrument USD_CAD --dry-run
```

Bot monitor GUI:

```bash
python scripts/run_bot_monitor.py
```

## Bot Flow

The simple bot follows this cycle:

1. Load persistent state from `data/bot_state.json`.
2. Fetch account summary and account details.
3. Fetch recent candles for one instrument.
4. Build a position-aware trade decision from moving averages.
5. Run health checks:
   - enough candles
   - candle freshness
   - open trade limits
   - failure backoff
   - policy validation
6. If safe, dry-run or submit an order through the practice-only execution engine.
7. Write the cycle record to `data/bot_audit.jsonl`.
8. Persist updated runtime state.

More detail:
- [docs/bot_logic.md](</C:/VS Code Workspaces/Oanda_SDK/docs/bot_logic.md>)
- [docs/current_status.md](</C:/VS Code Workspaces/Oanda_SDK/docs/current_status.md>)
- [docs/ai_experiment.md](</C:/VS Code Workspaces/Oanda_SDK/docs/ai_experiment.md>)

## Safety Model

The current bot is intentionally conservative:
- practice-only execution path
- dry-run by default
- single-instrument allowlist unless changed explicitly
- max units per trade
- max open trades
- required stop loss on entries
- cooldown between trade attempts
- repeated-failure backoff
- no stacking into the same direction blindly
- explicit close action before reversal

## Testing

Run targeted tests:

```bash
python -m pytest -q
```

## Near-Term Next Steps

- refine exit rules beyond simple trend reversal
- add spread-aware gating if pricing snapshots are included in the cycle
- add bot-performance summaries from audit logs
- add an oversight agent later without making it the only control point
