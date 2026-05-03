from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize saved backtest JSON files.")
    parser.add_argument(
        "--glob",
        default="data/backtest*.json",
        help="Glob pattern for backtest files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    files = sorted(Path(".").glob(args.glob))
    rows = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        summary = ((payload.get("replay") or {}).get("summary")) or {}
        gross_pnl = summary.get("gross_pnl", 0.0)
        net_pnl = summary.get("net_pnl", gross_pnl)
        expectancy = summary.get("expectancy", summary.get("avg_pnl_per_trade", 0.0))
        win_rate = summary.get("win_rate")
        if win_rate is None:
            trade_count = summary.get("trade_count", 0) or 0
            wins = summary.get("wins", 0) or 0
            win_rate = (wins / trade_count) if trade_count else 0.0
        max_drawdown = summary.get("max_drawdown", 0.0)
        rows.append(
            {
                "file": str(path),
                "instrument": payload.get("instrument"),
                "granularity": payload.get("granularity"),
                "trade_count": summary.get("trade_count", 0),
                "win_rate": win_rate,
                "gross_pnl": gross_pnl,
                "net_pnl": net_pnl,
                "expectancy": expectancy,
                "max_drawdown": max_drawdown,
                "setup_summary": ((payload.get("replay") or {}).get("setup_summary")) or {},
            }
        )

    if not rows:
        print("No backtest files matched.")
        return

    for row in rows:
        print(
            f"{row['file']} | {row['instrument']} {row['granularity']} | "
            f"trades={row['trade_count']} win_rate={row['win_rate']:.2%} "
            f"gross={row['gross_pnl']:.4f} net={row['net_pnl']:.4f} "
            f"expectancy={row['expectancy']:.4f} drawdown={row['max_drawdown']:.4f}"
        )
        if row["setup_summary"]:
            for setup, metrics in row["setup_summary"].items():
                print(
                    f"  setup={setup} trades={int(metrics.get('trade_count', 0))} "
                    f"win_rate={float(metrics.get('win_rate', 0.0)):.2%} "
                    f"net={float(metrics.get('net_pnl', 0.0)):.4f} "
                    f"expectancy={float(metrics.get('expectancy', 0.0)):.4f}"
                )


if __name__ == "__main__":
    sys.exit(main())
