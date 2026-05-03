"""
Run instrument candle checks and report candle counts/latency.
"""

from __future__ import annotations

import sys
import time

sys.path.insert(0, "src")

from oanda_autotrader.app import load_instruments_client


def timed(func):
    start = time.perf_counter()
    result = func()
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return result, elapsed_ms


def _summarize_candles(candles: list[dict]) -> dict[str, object]:
    if not candles:
        return {"count": 0, "complete": 0, "first_time": None, "last_time": None}
    complete_count = sum(1 for candle in candles if candle.get("complete") is True)
    first_time = candles[0].get("time")
    last_time = candles[-1].get("time")
    return {
        "count": len(candles),
        "complete": complete_count,
        "first_time": first_time,
        "last_time": last_time,
    }


def run(group: str, account_name: str, instrument: str):
    client = load_instruments_client("accounts.yaml", group, account_name)
    payload, ms = timed(
        lambda: client.get_candles(
            instrument,
            price="M",
            granularity="S5",
            count=6,
        )
    )
    candles = payload.get("candles", [])
    summary = _summarize_candles(candles)
    return {
        "group": group,
        "account": account_name,
        "instrument": instrument,
        "candles": summary["count"],
        "complete": summary["complete"],
        "first_time": summary["first_time"],
        "last_time": summary["last_time"],
        "ms": ms,
    }


def main():
    instruments = ["EUR_USD", "USD_CAD", "GBP_USD"]
    rows = []
    for instrument in instruments:
        rows.append(run("demo", "Primary", instrument))
        rows.append(run("live", "Primary", instrument))

    print("group\taccount\tinstrument\tcandles\tcomplete\tfirst_time\tlast_time\tms")
    for row in rows:
        print(
            f"{row['group']}\t{row['account']}\t{row['instrument']}\t{row['candles']}\t"
            f"{row['complete']}\t{row['first_time']}\t{row['last_time']}\t{row['ms']:.2f}"
        )


if __name__ == "__main__":
    main()
