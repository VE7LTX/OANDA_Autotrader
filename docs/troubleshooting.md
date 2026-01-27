# Troubleshooting

## Dashboard closes without QUIT
Symptoms:
- dashboard.log shows dashboard_tick lines but no pygame_quit_received
- window disappears without trace

Actions:
1) Run with faulthandler:
```bash
$env:PYTHONFAULTHANDLER="1"
python -X faulthandler -u scripts/dashboard_pygame.py
```
2) If still silent, check Windows Event Viewer for python.exe / SDL crashes.
3) Set OANDA_DASHBOARD_IGNORE_QUIT=true to rule out QUIT events.

## Predictions are stale (PRED: stale)
Check:
```bash
Get-Content data/predictions_latest.jsonl -Tail 1
```
If the timestamp is old, the prediction loop is not running or writing
somewhere else. Start it or check logs:
- data/prediction_runner.log

## Predictions offscale (PRED: offscale)
Check:
- pred_low/high vs price_min/max on the HUD
- base_close should be within a few pips of last candle close

If not, the prediction source does not match the candle series.

## Coverage/MAE stays null
This is expected until future candles exist.
For 5s candles and horizon=12, wait ~60s after the prediction timestamp.

## Stream latency p95 is 0.0
If stream latency p95 stays at 0.0:
- Check stream latency samples include effective_ms and clock_offset_ms.
- Ensure the monitor snapshot uses effective latency (not clamped raw).
- Verify `data/stream_latency.jsonl` has mode/instrument fields (new schema).

If thresholds are missing:
- `scripts/print_gate_config.py --mode live --instrument USD_CAD`
should report source=file. If it reports defaults, check
`config/latency_thresholds/`.

## warn toggling frequently
- `trade_gate.warn` and `warn_last` are spike-based (last_effective_ms).
- Use `warn_p95` for sustained warnings based on the windowed p95.

## No candle data / price scale is 0-1
Check candle files are updating:
```bash
Get-ChildItem data\usd_cad_candles_*.jsonl
Get-Content data\usd_cad_candles_*.jsonl -Tail 1
```
If timestamps are old, the capture/stream process is not running.

## Scorer not writing
Check that prediction_scores.jsonl is updating:
```bash
Get-Content data\prediction_scores.jsonl -Tail 3
```
If not, start the scorer:
```bash
python scripts/score_predictions.py --watch --every 10
```

## Recon axis looks wrong
The recon series is a reconstructed close (price units). If you need an
error axis, compute abs(close - recon) separately.

## Prediction/score logs missing
If data/prediction_runner.log or data/score_runner.log do not exist, verify
that dashboard autostart is enabled and the dashboard is launched from the repo
root (or uses the new cwd-safe autostart paths).
