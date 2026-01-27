# Data Contracts (JSONL)

All data exchange between scripts is JSONL. Each line is one JSON object.
Paths in this document assume the repo root.

## Candle files
Path pattern:
- data/usd_cad_candles_YYYYMMDD_HHMMSS.jsonl

Schema (per line):
- time: ISO timestamp
- complete: bool
- volume: int
- mid: object with o/h/l/c strings

Example:
```json
{"complete": true, "volume": 19, "time": "2026-01-26T00:47:30.000000000Z", "mid": {"o": "1.36912", "h": "1.36914", "l": "1.36910", "c": "1.36912"}}
```

Notes:
- The last line may have complete=false while a bucket is forming.

## Features file
Path:
- data/usd_cad_features.jsonl

Schema (per line):
- close, volume, vwap
- return, log_return
- indicators: sma_fast, sma_slow, ema_fast, ema_slow, rsi, macd, macd_signal,
  macd_hist, bb_mid, bb_upper, bb_lower, bb_width, atr, plus_di, minus_di,
  adx, stoch_k, stoch_d, obv

Example:
```json
{"close":1.36912,"volume":19,"vwap":1.36911,"return":0.00001,"log_return":0.00001,"sma_fast":1.36910,"sma_slow":1.36905}
```

## Predictions (latest)
Path:
- data/predictions_latest.jsonl (single-line overwrite)

Schema:
- ts: ISO timestamp
- model_version
- interval_secs
- horizon_secs
- base_close
- k: band multiplier
- pred_std: list (per step)
- horizon: list of step objects

Horizon step fields:
- step
- mu (delta)
- sigma (per-step std)
- mean (base + cumulative delta)
- low/high (mean +/- k * cumulative sigma)

Example:
```json
{"ts":"2026-01-26T15:44:23Z","interval_secs":5,"horizon_secs":60,"base_close":1.36916,"k":1.5,"horizon":[{"step":1,"mu":0.00001,"sigma":0.00003,"mean":1.36917,"low":1.36912,"high":1.36922}]}
```

## Predictions (archive)
Path pattern:
- data/predictions/predictions_YYYYMMDD_HHMM.jsonl

Same schema as predictions_latest.jsonl. Used for history/analysis.

## Prediction scores
Path:
- data/prediction_scores.jsonl (append)

Schema:
- ts: prediction timestamp
- coverage, mae
- results: list of step objects (step, actual, hit)
- buckets: list of bucket summaries (label, coverage, mae, resolved)
- scored_ts

Example:
```json
{"ts":"2026-01-26T15:44:23Z","coverage":0.5,"mae":0.00002,"results":[{"step":1,"actual":1.36915,"hit":true}],"buckets":[{"label":"1-3","coverage":0.5,"mae":0.00002,"resolved":2}],"scored_ts":"2026-01-26T15:45:23Z"}
```

## Recon status
Path:
- data/recon.jsonl

Schema:
- ts
- actual (close)
- recon (reconstructed close, price units)
- error, mean_error, std_error
- k (band multiplier)

## AE status
Path:
- data/ae_status.jsonl

Schema:
- ts
- epoch
- loss
- val_loss (optional)
- pred_loss (optional)
- device

## Stream latency samples
Path:
- data/stream_latency.jsonl

Schema:
- ts (ISO)
- mode (live|practice)
- instrument (e.g., USD_CAD)
- received_ts (epoch seconds)
- server_time (ISO from stream)
- latency_ms_raw
- latency_ms_clamped
- effective_ms
- clock_offset_ms
- skew_ms
- is_backlog
- is_outlier

## Monitoring snapshots
Path:
- data/monitor.jsonl

Schema:
- ts
- rest (per-name latency stats)
- stream (StreamMetrics snapshot)
- trade_gate (TradeLatencyGate snapshot)

Stream snapshot fields include:
- latency_last_ms / latency_p95_ms / latency_mean_ms (effective)
- latency_clamped_last_ms / latency_clamped_p95_ms / latency_clamped_mean_ms
- latency_effective_last_ms / latency_effective_p95_ms / latency_effective_mean_ms

Trade gate fields include:
- warn (backward-compatible; same as warn_last)
- warn_last (instantaneous spike based on last_effective_ms)
- warn_p95 (sustained warning based on effective_p95_ms)
- effective_p95_ms / effective_mean_ms (windowed stats for gate)

## Logs
- data/dashboard.log (dashboard lifecycle + pygame events)
- data/prediction_runner.log (prediction subprocess stdout/stderr)
- data/score_runner.log (scoring subprocess stdout/stderr)
