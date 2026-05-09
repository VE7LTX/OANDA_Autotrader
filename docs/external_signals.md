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
- `polymarket`: reads public Gamma event/market probabilities and maps them to
  instrument direction when a configured threshold is crossed.
- `santiment`: reads GraphQL metrics when `SANTIMENT_API_KEY` or `SANAPI_KEY`
  is present, then maps large metric changes to configured direction.

## Candidate Sources

- OANDA Technical Analysis: useful because it is broker-native and already
  focused on chart patterns, Fibonacci, support/resistance, and volatility.
  Treat it as a confluence feed if alerts can be exported or entered manually.
- Polymarket: useful for macro event probabilities, central-bank expectations,
  election/geopolitical risk, crypto sentiment, and risk-on/risk-off context.
  It is not a direct FX signal feed.
- Santiment: useful for crypto and social/on-chain risk proxies. It is most
  relevant to crypto-linked sentiment and broader speculative appetite, not
  direct CAD/JPY/EUR signals.

## Research Rules

- External signals should never bypass base submit thresholds.
- External signals can boost an already-valid candidate or penalize a candidate
  that conflicts with external context.
- Every provider must write normalized signals first, then be backtested against
  candle outcomes before being allowed into live practice mode.
- Provider outages or stale signals should degrade to no adjustment.
