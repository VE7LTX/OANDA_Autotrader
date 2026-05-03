from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from oanda_autotrader.app import build_instruments_client
from oanda_autotrader.config import (
    load_account_groups_or_default,
    resolve_account_credentials,
    select_account,
)

from scripts.backtest_open_window import parse_ts, replay_window


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the same backtest across multiple window starts.")
    parser.add_argument("--accounts-path", default="accounts.yaml")
    parser.add_argument("--group", default="demo")
    parser.add_argument("--account", default="Primary")
    parser.add_argument("--instrument", default="USD_CAD")
    parser.add_argument("--granularity", default="M5")
    parser.add_argument("--window-hours", type=int, default=48)
    parser.add_argument("--fetch-count", type=int, default=600)
    parser.add_argument("--window-starts", default="")
    parser.add_argument("--window-starts-file")
    parser.add_argument("--output-dir", default="data/batch_backtests")
    parser.add_argument("--aggregate-output", default="data/batch_backtests/summary.json")
    parser.add_argument("--fast-window", type=int, default=5)
    parser.add_argument("--slow-window", type=int, default=20)
    parser.add_argument("--max-open-trades", type=int, default=1)
    parser.add_argument("--max-units", type=int, default=100)
    parser.add_argument("--risk-per-trade-fraction", type=float, default=0.0025)
    parser.add_argument("--long-score-threshold", type=float, default=2.25)
    parser.add_argument("--short-score-threshold", type=float, default=2.0)
    parser.add_argument("--regime-score-threshold", type=float, default=1.0)
    parser.add_argument("--trailing-atr-multiple", type=float, default=1.25)
    parser.add_argument("--break-even-atr-multiple", type=float, default=1.0)
    parser.add_argument("--max-hold-candles", type=int, default=24)
    parser.add_argument("--spread-pips", type=float, default=0.00008)
    parser.add_argument("--slippage-pips", type=float, default=0.00002)
    parser.add_argument("--allowed-hours-utc", default="21,22,23,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    window_starts = resolve_window_starts(args.window_starts, args.window_starts_file)
    if not window_starts:
        raise SystemExit("No window starts provided.")

    groups = load_account_groups_or_default(args.accounts_path)
    group, entry = select_account(groups, args.group, args.account)
    app_config = resolve_account_credentials(group, entry)
    client = build_instruments_client(app_config)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for window_start in window_starts:
        window_end = (parse_ts(window_start) + timedelta(hours=args.window_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = client.get_candles(
            args.instrument,
            price="M",
            granularity=args.granularity,
            count=args.fetch_count,
            time_to=window_end,
        )
        candles = payload.get("candles", [])
        replay_args = build_replay_args(args, window_start, window_end)
        replay = replay_window(candles, replay_args)
        output_path = output_dir / output_name(args.instrument, args.granularity, window_start)
        result = {
            "instrument": args.instrument,
            "granularity": args.granularity,
            "window_start_utc": window_start,
            "window_end_utc": window_end,
            "window_hours": args.window_hours,
            "fetched_candles": len(candles),
            "candles": candles,
            "replay": replay,
        }
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        summary = replay.get("summary", {})
        rows.append(
            {
                "window_start_utc": window_start,
                "window_end_utc": window_end,
                "output": str(output_path),
                "trade_count": summary.get("trade_count", 0),
                "win_rate": summary.get("win_rate", 0.0),
                "net_pnl": summary.get("net_pnl", 0.0),
                "expectancy": summary.get("expectancy", 0.0),
                "max_drawdown": summary.get("max_drawdown", 0.0),
            }
        )

    aggregate = {
        "instrument": args.instrument,
        "granularity": args.granularity,
        "window_hours": args.window_hours,
        "window_count": len(rows),
        "windows": rows,
    }
    aggregate_path = Path(args.aggregate_output)
    aggregate_path.parent.mkdir(parents=True, exist_ok=True)
    aggregate_path.write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    print(json.dumps(aggregate, indent=2))


def resolve_window_starts(raw: str, file_path: str | None) -> list[str]:
    values: list[str] = []
    if raw:
        values.extend([item.strip() for item in raw.split(",") if item.strip()])
    if file_path:
        values.extend(
            [
                line.strip()
                for line in Path(file_path).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        )
    return values


def build_replay_args(args: argparse.Namespace, window_start: str, window_end: str) -> SimpleNamespace:
    return SimpleNamespace(
        instrument=args.instrument,
        granularity=args.granularity,
        window_start=window_start,
        window_end=window_end,
        window_hours=args.window_hours,
        fetch_count=args.fetch_count,
        fast_window=args.fast_window,
        slow_window=args.slow_window,
        units=args.max_units,
        max_units=args.max_units,
        max_open_trades=args.max_open_trades,
        risk_per_trade_fraction=args.risk_per_trade_fraction,
        long_score_threshold=args.long_score_threshold,
        short_score_threshold=args.short_score_threshold,
        regime_score_threshold=args.regime_score_threshold,
        trailing_atr_multiple=args.trailing_atr_multiple,
        break_even_atr_multiple=args.break_even_atr_multiple,
        max_hold_candles=args.max_hold_candles,
        spread_pips=args.spread_pips,
        slippage_pips=args.slippage_pips,
        allowed_hours_utc=args.allowed_hours_utc,
    )


def output_name(instrument: str, granularity: str, window_start: str) -> str:
    safe_start = window_start.replace(":", "").replace("-", "").replace("T", "_").replace("Z", "")
    return f"backtest_{instrument.lower()}_{granularity.lower()}_{safe_start}.json"


if __name__ == "__main__":
    main()
