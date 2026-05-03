"""
Run quick health checks against OANDA accounts and report counts.

Outputs:
- Accounts list count
- Instrument count
- Open orders/trades/positions counts
- Latency per call
"""

from __future__ import annotations

import sys
import time

sys.path.insert(0, "src")

from collections import Counter

from oanda_autotrader.app import load_account_client
from oanda_autotrader.config import load_account_groups, select_account


def timed(label: str, func):
    start = time.perf_counter()
    result = func()
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return result, elapsed_ms


def run(group: str, account_name: str):
    client = load_account_client("accounts.yaml", group, account_name)

    accounts_payload, accounts_ms = timed("accounts", client.list_accounts)
    groups = load_account_groups("accounts.yaml")
    selected_group, selected_entry = select_account(groups, group, account_name)
    account_id = selected_entry.account_id

    details_payload, details_ms = timed(
        "details", lambda: client.get_account(account_id)
    )
    summary_payload, summary_ms = timed(
        "summary", lambda: client.get_account_summary(account_id)
    )
    instruments_payload, instruments_ms = timed(
        "instruments", lambda: client.get_instruments(account_id)
    )

    accounts_count = len(accounts_payload.get("accounts", []))
    instruments = instruments_payload.get("instruments", [])
    instruments_count = len(instruments)
    instrument_types = Counter(
        instrument.get("type", "UNKNOWN") for instrument in instruments
    )
    orders_count = len(details_payload.get("account", {}).get("orders", []))
    trades_count = len(details_payload.get("account", {}).get("trades", []))
    positions_count = len(details_payload.get("account", {}).get("positions", []))

    return {
        "group": group,
        "account_name": account_name,
        "account_id": account_id,
        "accounts_count": accounts_count,
        "instruments_count": instruments_count,
        "instrument_types": dict(instrument_types),
        "orders_count": orders_count,
        "trades_count": trades_count,
        "positions_count": positions_count,
        "latency_ms": {
            "accounts": accounts_ms,
            "details": details_ms,
            "summary": summary_ms,
            "instruments": instruments_ms,
        },
    }


def main():
    rows = [
        run("demo", "Primary"),
        run("live", "Primary"),
    ]

    header = (
        "group\taccount\tid\taccounts\tinstruments\torders\ttrades\tpositions\t"
        "ms_accounts\tms_details\tms_summary\tms_instruments\tinstrument_types"
    )
    print(header)
    for row in rows:
        ms = row["latency_ms"]
        print(
            f"{row['group']}\t{row['account_name']}\t{row['account_id']}\t"
            f"{row['accounts_count']}\t{row['instruments_count']}\t"
            f"{row['orders_count']}\t{row['trades_count']}\t{row['positions_count']}\t"
            f"{ms['accounts']:.2f}\t{ms['details']:.2f}\t{ms['summary']:.2f}\t{ms['instruments']:.2f}\t"
            f"{row['instrument_types']}"
        )


if __name__ == "__main__":
    main()
