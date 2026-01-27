# Runbooks

## Development (offline/unit tests)
```bash
pip install -r requirements-dev.txt
pytest
```

## Live checks (requires credentials)
```bash
set RUN_LIVE_TESTS=1
pytest -m live
```

## Connectivity checks
```bash
python scripts/run_checks.py
python scripts/run_instrument_checks.py
```

## End-to-end (manual)
1) Start candle capture:
```bash
python scripts/capture_usd_cad_stream.py
```

Note: `practice` is an alias of the `demo` account group for account selection.

2) Build features (if needed):
```bash
python scripts/build_features.py --input-dir data --output data/usd_cad_features.jsonl
```

3) Start prediction loop:
```bash
python scripts/train_autoencoder_loop.py --features data/usd_cad_features.jsonl --retrain-interval 60 --epochs 1 --horizon 12 --interval-secs 5
```

4) Start scoring:
```bash
python scripts/score_predictions.py --watch --every 10
```

5) Launch dashboard:
```bash
python scripts/dashboard_pygame.py
```

## End-to-end (dashboard autostart)
The dashboard can autostart prediction + scoring helpers:
```bash
python scripts/dashboard_pygame.py
```

Optional environment overrides:
- OANDA_DASHBOARD_AUTOSTART=false
- OANDA_DASHBOARD_PRED_FEATURES=data/usd_cad_features.jsonl
- OANDA_DASHBOARD_PRED_RETRAIN_INTERVAL=60
- OANDA_DASHBOARD_SCORE_EVERY=10

## Latency profile calibration (120s)
```bash
python scripts/capture_latency.py --mode live --instrument USD_CAD --seconds 120
python scripts/calc_latency_profile.py --source stream --mode live --instrument USD_CAD --since-seconds 180 --legacy-ok
```

This writes:
- `data/latency_profile_live_USD_CAD.json`

Detached capture (survives terminal close):
```powershell
scripts\launch_capture.ps1 -Mode live -Instrument USD_CAD -Seconds 600
```

The launcher writes the capture PID to:
- `data/capture_<mode>_<instrument>.pid`
## Detached dashboard (survives terminal close)
```powershell
scripts\launch_dashboard.ps1
```

Options:
- `-UsePythonw` (no console window)
- `-IgnoreQuit` (ignore QUIT events for debugging)
- `-WorkingDir` (override repo root)
- `-RedirectLogs` (write stdout/stderr to files)
- `-StdoutPath` / `-StderrPath` (override log paths)

The launcher writes the dashboard PID to:
- `data/dashboard.pid`

## Scoring delay note
Scoring is delayed by definition. For 5s candles and horizon=12, you need
~60s of future candles before coverage/MAE resolve.
