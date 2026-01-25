# Health Checks

## Purpose
The health check script verifies connectivity, reports counts, and measures latency.

## Script
- `scripts/run_checks.py`

## Output Columns
- `group`: account group from `accounts.yaml` (demo/live).
- `account`: account name in the group.
- `id`: account ID (from `accounts.yaml`).
- `accounts`: number of accounts returned by `GET /v3/accounts`.
- `instruments`: number of instruments returned by `GET /v3/accounts/{accountID}/instruments`.
- `orders`: open orders count from account details.
- `trades`: open trades count from account details.
- `positions`: open positions count from account details.
- `ms_*`: latency per endpoint (milliseconds).
- `instrument_types`: counts grouped by instrument type (CURRENCY/CFD/METAL).

## Notes
- The script uses the account ID from `accounts.yaml` (not the first returned ID).
- Enable `OANDA_DEBUG_LOGGING=true` to see per-request logs.
