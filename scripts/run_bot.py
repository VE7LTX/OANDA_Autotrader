from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from oanda_autotrader.bot import BotConfig, SimpleTradingBot
from oanda_autotrader.config import (
    load_account_groups_or_default,
    resolve_account_credentials,
    select_account,
)
from oanda_autotrader.execution import RiskPolicy
from oanda_autotrader.health import HealthConfig
from oanda_autotrader.strategy import StrategyConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the simple practice trading bot.")
    parser.add_argument("--accounts-path", default="accounts.yaml")
    parser.add_argument("--group", default="demo")
    parser.add_argument("--account", default="Primary")
    parser.add_argument("--instrument", default="USD_CAD")
    parser.add_argument("--granularity", default="M5")
    parser.add_argument("--count", type=int, default=120)
    parser.add_argument("--fast-window", type=int, default=5)
    parser.add_argument("--slow-window", type=int, default=20)
    parser.add_argument("--units", type=int, default=100)
    parser.add_argument("--risk-per-trade-fraction", type=float, default=0.0025)
    parser.add_argument("--long-score-threshold", type=float, default=2.25)
    parser.add_argument("--short-score-threshold", type=float, default=2.0)
    parser.add_argument("--regime-score-threshold", type=float, default=1.0)
    parser.add_argument("--trailing-atr-multiple", type=float, default=1.25)
    parser.add_argument("--break-even-atr-multiple", type=float, default=1.0)
    parser.add_argument("--max-hold-candles", type=int, default=24)
    parser.add_argument("--cooldown-seconds", type=int, default=300)
    parser.add_argument("--min-confidence", type=float, default=0.55)
    parser.add_argument("--max-open-trades", type=int, default=1)
    parser.add_argument("--max-units", type=int, default=100)
    parser.add_argument("--max-staleness-seconds", type=int, default=900)
    parser.add_argument("--min-atr", type=float, default=0.00015)
    parser.add_argument("--max-daily-loss", type=float, default=250.0)
    parser.add_argument("--max-weekly-loss", type=float, default=750.0)
    parser.add_argument("--allowed-hours-utc", default="0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--audit-path", default="data/bot_audit.jsonl")
    parser.add_argument("--state-path", default="data/bot_state.json")
    parser.add_argument("--failure-backoff-seconds", type=int, default=600)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--submit", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    groups = load_account_groups_or_default(args.accounts_path)
    group, entry = select_account(groups, args.group, args.account)
    app_config = resolve_account_credentials(group, entry)

    bot = SimpleTradingBot(
        app_config,
        bot_config=BotConfig(
            instrument=args.instrument,
            granularity=args.granularity,
            candle_count=args.count,
            cooldown_seconds=args.cooldown_seconds,
            audit_path=args.audit_path,
            state_path=args.state_path,
            failure_backoff_seconds=args.failure_backoff_seconds,
        ),
        strategy_config=StrategyConfig(
            instrument=args.instrument,
            fast_window=args.fast_window,
            slow_window=args.slow_window,
            units=args.max_units,
            risk_per_trade_fraction=args.risk_per_trade_fraction,
            long_score_threshold=args.long_score_threshold,
            short_score_threshold=args.short_score_threshold,
            regime_score_threshold=args.regime_score_threshold,
            trailing_atr_multiple=args.trailing_atr_multiple,
            break_even_atr_multiple=args.break_even_atr_multiple,
            max_hold_candles=args.max_hold_candles,
        ),
        risk_policy=RiskPolicy(
            practice_only=True,
            allowed_instruments=(args.instrument,),
            max_units_per_trade=args.max_units,
            max_open_trades=args.max_open_trades,
            min_confidence=args.min_confidence,
        ),
        health_config=HealthConfig(
            min_candles=args.slow_window,
            max_staleness_seconds=args.max_staleness_seconds,
            min_atr=args.min_atr,
            max_daily_loss=args.max_daily_loss,
            max_weekly_loss=args.max_weekly_loss,
            min_regime_score=args.regime_score_threshold,
            allowed_hours_utc=tuple(
                int(x) for x in args.allowed_hours_utc.split(",") if str(x).strip() != ""
            ),
        ),
    )

    dry_run = not args.submit or args.dry_run
    for idx in range(args.iterations):
        record = bot.run_cycle(dry_run=dry_run)
        print(json.dumps(record, indent=2))
        if idx + 1 < args.iterations:
            time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
