# OANDA_Autotrader
AUTO Forex Trader Project

## Overview
This repo is a segmented scaffold for OANDA v20 REST + streaming usage with:
- sync and async HTTP clients
- account endpoints (list/details/summary/instruments)
- streaming client with reconnect/backoff
- latency monitoring and health checks

## Quick Start
1) Copy sample config files and rename them:
   - `accounts.yaml.example` -> `accounts.yaml`
   - `.env.example` -> `.env`
2) Edit the new files with your real credentials.
3) Install deps:
```bash
pip install -r requirements.txt
```

Note: The real config files are gitignored to prevent accidental leaks.

## Project Layout
- `src/oanda_autotrader/config.py`: loads `accounts.yaml`, resolves env vars, builds AppConfig/AppSettings.
- `src/oanda_autotrader/http.py`: sync HTTP client with rate limiting + debug logging.
- `src/oanda_autotrader/async_http.py`: async HTTP client (aiohttp).
- `src/oanda_autotrader/endpoints/accounts.py`: sync account endpoints.
- `src/oanda_autotrader/endpoints/accounts_async.py`: async account endpoints.
- `src/oanda_autotrader/app.py`: client builders + validation + stream wiring.
- `src/oanda_autotrader/streaming.py`: HTTP streaming client with reconnect/backoff.
- `src/oanda_autotrader/models.py`: typed stream message wrappers.
- `src/oanda_autotrader/monitor.py`: latency sampling helpers.
- `src/oanda_autotrader/logging_config.py`: structured logging setup.
- `scripts/run_checks.py`: health check report with counts and timings.
- `scripts/capture_usd_cad_candles.py`: JSONL candle export for model training.

## Endpoints Covered
Accounts:
- `GET /v3/accounts`
- `GET /v3/accounts/{accountID}`
- `GET /v3/accounts/{accountID}/summary`
- `GET /v3/accounts/{accountID}/instruments`

Streaming:
- `GET /v3/accounts/{accountID}/pricing/stream`
- `GET /v3/accounts/{accountID}/transactions/stream`

Instruments:
- `GET /v3/instruments/{instrument}/candles`

## Example Usage (Sync)
```python
from oanda_autotrader.app import load_account_client

client = load_account_client("accounts.yaml", "demo", "Primary")
print(client.list_accounts())
```

```python
from oanda_autotrader.app import validate_account_connection

result = validate_account_connection("accounts.yaml", "demo", "Primary")
print(result)
```

## Example Usage (Async)
```python
import asyncio
from oanda_autotrader.app import load_account_client_async

async def main():
    client = load_account_client_async("accounts.yaml", "demo", "Primary")
    async with client._client:
        print(await client.list_accounts())

asyncio.run(main())
```

## Streaming Example
```python
import asyncio
from oanda_autotrader.config import load_account_groups, select_account, resolve_account_credentials
from oanda_autotrader.app import build_stream_client

async def main():
    groups = load_account_groups("accounts.yaml")
    group, entry = select_account(groups, "live", "Primary")
    config = resolve_account_credentials(group, entry)
    async with build_stream_client(config) as stream:
        async for msg in stream.stream_pricing(entry.account_id, ["EUR_USD"]):
            print(msg)

asyncio.run(main())
```

## Health Check Report
Run:
```bash
python scripts/run_checks.py
```

Report columns:
- `group`, `account`, `id`: account identifiers.
- `accounts`: count of accessible accounts.
- `instruments`: number of tradeable instruments.
- `orders`, `trades`, `positions`: counts from account details.
- `ms_*`: per-endpoint latency (milliseconds).
- `instrument_types`: counts by type (CURRENCY/CFD/METAL).
More details: `CHECKS.md`.

## Data Capture (USD_CAD)
```bash
python scripts/capture_usd_cad_candles.py
```

## Instrument Check
```bash
python scripts/run_instrument_checks.py
```

## Performance & Reliability
Defaults and tuning are in `CONFIG.md`. Key points:
- Rate limiting: `OANDA_REQUESTS_PER_SECOND` (default 100).
- Debug logging: `OANDA_DEBUG_LOGGING` (default false).
- Stream reconnect/backoff: `OANDA_STREAM_*` (defaults in `.env.example`).
 - Structured logs: `setup_logging(json_output=True)` for JSONL output.

## Reference Docs
- `BEST_PRACTICES.md`: OANDA best practices + sync pattern.
- `STREAMING.md`: stream behavior, reconnect strategy.
- `CONFIG.md`: env config reference.
- `CHECKS.md`: health check output and usage notes.
- `TODO.md`: roadmap and next improvements.
