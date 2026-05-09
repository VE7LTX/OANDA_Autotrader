# External Signal Integration

External feeds should be used as bounded context, not as direct trade triggers.
The scanner still requires its normal candle, scorecard, spread, exposure, and
risk gates before an external signal can improve candidate ranking.

## Signal File

The scanner reads `data/external_signals.json` by default. Keep live files under
`data/` so they stay out of git. Use `external_signals.example.json` as the
editable template.

```json
{
  "generated_at": "2026-05-09T00:00:00Z",
  "signals": [
    {
      "source": "manual",
      "instrument": "EUR_USD",
      "direction": "bullish",
      "confidence": 0.65,
      "reason": "Macro context favors EUR over USD."
    }
  ]
}
```

Supported fields:

- `instrument`: OANDA instrument name, such as `EUR_USD`.
- `instruments`: optional list of OANDA instrument names.
- `direction`: `bullish`, `bearish`, `buy`, `sell`, `long`, or `short`.
- `confidence`: `0.0` to `1.0`; converted to a bounded score adjustment.
- `score_adjustment`: optional explicit adjustment cap per signal.
- `timestamp`: optional per-signal freshness timestamp.
- `source`, `reason`, `title`, `market`: recorded for audit/debugging.

Useful scanner options:

```powershell
python scripts\scan_forex_opportunities.py --external-signals-path data\external_signals.json --external-signal-max-adjustment 0.75 --external-signal-max-age-minutes 240
```

## Collector

Use `scripts/collect_external_signals.py` to convert configured sources into
the scanner signal file:

```powershell
python scripts\collect_external_signals.py --config external_signal_sources.example.json --output data\external_signals.json
```

The collector currently supports:

- `manual`: copied into the output after normalization.
- `oanda`: imports OANDA Technical Analysis / Autochartist alerts copied or
  exported to JSON/CSV, then normalizes fields like instrument, direction,
  confidence, pattern, target price, and timestamp.
- `polymarket`: reads public Gamma event/market probabilities and maps them to
  instrument direction when a configured threshold is crossed.

## Candidate Sources

- OANDA Technical Analysis: useful because it is broker-native and already
  focused on chart patterns, Fibonacci, support/resistance, and volatility.
  Treat it as a confluence feed. OANDA describes this as Technical Analysis
  powered by Autochartist inside OANDA Trade, not as a normal v20 trading API
  endpoint, so this project imports exported/copied alerts rather than scraping
  the trading platform.
- Polymarket: useful for macro event probabilities, central-bank expectations,
  election/geopolitical risk, crypto sentiment, and risk-on/risk-off context.
  It is not a direct FX signal feed.

## Research Rules

- External signals should never bypass base submit thresholds.
- External signals can boost an already-valid candidate or penalize a candidate
  that conflicts with external context.
- Every provider must write normalized signals first, then be backtested against
  candle outcomes before being allowed into live practice mode.
- Provider outages or stale signals should degrade to no adjustment.

## OANDA Signal Import

Put OANDA Technical Analysis / Autochartist alerts into JSON or CSV and point
`external_signal_sources.example.json` at that file.

JSON example:

```json
{
  "signals": [
    {
      "source": "oanda_autochartist",
      "instrument": "EUR_USD",
      "direction": "bullish",
      "confidence": 0.64,
      "pattern": "Fibonacci pattern",
      "timestamp": "2026-05-09T00:00:00Z"
    }
  ]
}
```

CSV columns can use common names such as `instrument`, `symbol`, `direction`,
`bias`, `confidence`, `quality`, `pattern`, `target_price`, `current_price`,
and `timestamp`. If direction is missing, the collector infers bullish/bearish
from `target_price` versus `current_price`.
