# Weekend Opportunity Research

Use weekends to replay cached OANDA candles and tune deterministic gates before
the next live practice-account run. The goal is not to maximize trade count. The
goal is to improve positive expectancy, profit factor, and drawdown while keeping
enough trades to avoid one-off curve fitting.

## Current Best Offline Result

Dataset:

- `data/research_last_week_candles.json`
- 7 calendar days of cached candles
- 99 instruments: FX, metals, and commodities
- Granularities: `M5`, `M15`, `H1`

Best focused sweep on 2026-05-09:

- Trades: `658`
- Win rate: `39.7%`
- Profit factor: `1.19`
- Net R: `+76.83R`
- Max drawdown: `-18.83R`

Best settings:

```text
min_submit_score=5.4
non_liquid_min_submit_score=6.0
max_spread_atr_ratio=0.65
higher_timeframe_confirmation=enabled
higher_timeframe_min_agreements=1
higher_timeframe_agreement_bonus=0.35
higher_timeframe_max_score_bonus=0.75
entry_timing_confirmation=disabled
```

Interpretation:

- M15/H1 confirmation helped materially. Disabling it turned the same family of
  settings negative or much weaker.
- Higher-timeframe agreement is now treated as confluence, not only a binary
  gate. Aligned timeframes can add a bounded score bonus, while conflicts reduce
  score and still block by default.
- The confluence bonus is applied after the base submit threshold. It is meant
  to rank already-valid setups, not to admit marginal trades.
- The current M5 entry-timing confirmation is too restrictive or mistimed for
  this strategy. It reduced trades but did not improve expectancy in the replay.
- The 60% broad-universe win-rate target is not realistic with the current
  formula. The better near-term target is positive expectancy with controlled
  drawdown, then instrument-level filtering.
- Stronger instruments in this replay included `GBP_JPY`, `EUR_AUD`,
  `EUR_NZD`, `CAD_JPY`, `GBP_NZD`, and `NZD_JPY`.
- Weak instruments in this replay included `GBP_USD`, `GBP_AUD`, `NZD_USD`,
  `USD_CAD`, `EUR_NOK`, `USD_PLN`, and `USD_THB`.

## Commands

Refresh the 7-day candle cache:

```powershell
$env:PYTHONPATH='src'
python scripts\research_opportunity_patterns.py --group demo --account Primary --days 7 --include-metals --include-commodities --cache-path data\research_last_week_candles.json --download-only
```

Run the focused comparison:

```powershell
$env:PYTHONPATH='src'
python scripts\research_opportunity_patterns.py --use-cache --cache-path data\research_last_week_candles.json --output data\research_last_week_focused_results.json --include-metals --include-commodities --min-submit-scores 5.4 --non-liquid-min-submit-scores 5.75 --metal-submit-adds 0.45 --commodity-submit-adds 0.55 --max-spread-atr-ratios 0.80 --entry-extension-atrs 1.0,1.35,1.75 --htf-min-agreements 1 --top 12 --min-trades 20
```

Run the current best targeted sweep:

```powershell
$env:PYTHONPATH='src'
python scripts\research_opportunity_patterns.py --use-cache --cache-path data\research_last_week_candles.json --output data\research_last_week_timing_disabled_sweep.json --include-metals --include-commodities --disable-entry-timing-confirmation --min-submit-scores 5.2,5.4,5.6 --non-liquid-min-submit-scores 5.75,6.0 --metal-submit-adds 0.45 --commodity-submit-adds 0.55 --max-spread-atr-ratios 0.65,0.80 --entry-extension-atrs 1.35 --htf-min-agreements 1,2 --top 16 --min-trades 20
```

## Next Research Steps

- Add instrument whitelist and blacklist replay modes so weak symbols can be
  excluded before live practice execution.
- Split reporting by instrument class: major FX, minor FX, exotic FX, metals,
  and commodities.
- Add walk-forward validation: tune on the first half of the week and score on
  the second half before accepting settings.
- Replace the binary M5 entry-timing gate with a pullback-aware timing score so
  clean trend continuation is not blocked just because one candle is not ideal.
- Add per-instrument scorecard replay so quarantine logic can be tested offline,
  not only during live practice runs.
