# Bot Logic

## Current Decision Logic

The current bot uses a deterministic moving-average crossover strategy.

Inputs:
- recent `M5` candles for one instrument
- current account snapshot
- current open position for that instrument

Core signals:
- fast moving average
- slow moving average
- distance between those moving averages

Actions:
- `buy`: fast MA is meaningfully above slow MA and there is no existing long
- `sell`: fast MA is meaningfully below slow MA and there is no existing short
- `hold`: not enough data, weak signal, or already in the same direction
- `close`: there is an open position and the signal now points the other way

## Position-Aware Behavior

The bot does not keep piling into the same direction.

Examples:
- already long + bullish signal -> `hold`
- already short + bearish signal -> `hold`
- long + bearish reversal -> `close`
- short + bullish reversal -> `close`

This keeps the first implementation simpler and safer than immediate reversal in
one cycle.

## Safety Gates Before Execution

Even if the strategy wants to trade, the bot still blocks itself when:
- the candle set is too small
- the newest candle is stale
- the account already exceeds the configured open-trade cap
- recent failures triggered backoff
- the execution policy rejects the trade

## Why It Blocked On Sunday

During the Sunday pre-open period, account access may work while tradable FX
candles are still stale. In that state the bot should refuse to act. That is
expected and correct behavior.

## How It Learns Today

Strictly speaking, it does not learn from mistakes yet.

What it does today:
- records every cycle to `data/bot_audit.jsonl`
- records runtime state to `data/bot_state.json`
- preserves the exact action, health result, and blocking reason

That means it is **observable**, but not yet adaptive.

## How It Should Learn Next

The safe path is offline learning first, not self-modifying live behavior.

Recommended progression:

1. Collect audit logs for many dry-run and practice sessions.
2. Score each decision against later market movement.
3. Measure:
   - win/loss rate
   - average favorable excursion
   - average adverse excursion
   - blocking frequency
   - signal quality by session and instrument
4. Use that analysis to tune:
   - fast/slow MA windows
   - minimum signal separation
   - stop loss distance
   - take profit distance
   - cooldown and backoff thresholds
5. Only after that, consider a higher-level oversight model that can veto or
   down-rank trades.

The key point: the bot should learn by **policy refinement from logs**, not by
live unconstrained self-editing.
