from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
from oanda_autotrader.execution import AccountSnapshot, RiskPolicy, TradeAction
from oanda_autotrader.health import HealthConfig, evaluate_bot_health
from oanda_autotrader.indicators import atr
from oanda_autotrader.strategy import StrategyConfig, moving_average_crossover


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch and replay an opening-window candle set against the current bot logic."
    )
    parser.add_argument("--accounts-path", default="accounts.yaml")
    parser.add_argument("--group", default="demo")
    parser.add_argument("--account", default="Primary")
    parser.add_argument("--instrument", default="USD_CAD")
    parser.add_argument("--granularity", default="M5")
    parser.add_argument("--window-start", default="2026-04-26T21:05:00Z")
    parser.add_argument("--window-end")
    parser.add_argument("--window-hours", type=int, default=48)
    parser.add_argument("--fetch-count", type=int, default=600)
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
    parser.add_argument("--max-open-trades", type=int, default=1)
    parser.add_argument("--max-units", type=int, default=100)
    parser.add_argument("--spread-pips", type=float, default=0.00008)
    parser.add_argument("--slippage-pips", type=float, default=0.00002)
    parser.add_argument("--allowed-hours-utc", default="21,22,23,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16")
    parser.add_argument(
        "--output",
        default="data/backtest_usd_cad_open_2026-04-26.json",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Only fetch and store candles without replaying the strategy.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.window_end:
        args.window_end = (
            parse_ts(args.window_start) + timedelta(hours=args.window_hours)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    groups = load_account_groups_or_default(args.accounts_path)
    group, entry = select_account(groups, args.group, args.account)
    app_config = resolve_account_credentials(group, entry)
    client = build_instruments_client(app_config)

    payload = client.get_candles(
        args.instrument,
        price="M",
        granularity=args.granularity,
        count=args.fetch_count,
        time_to=args.window_end,
    )
    candles = payload.get("candles", [])
    result: dict[str, object] = {
        "instrument": args.instrument,
        "granularity": args.granularity,
        "window_start_utc": args.window_start,
        "window_end_utc": args.window_end,
        "window_start_new_york": "2026-04-26 17:05:00 America/New_York",
        "window_hours": args.window_hours,
        "fetched_candles": len(candles),
        "candles": candles,
    }

    if not args.download_only:
        result["replay"] = replay_window(candles, args)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "candles"}, indent=2))
    print(f"wrote {output}")


def replay_window(candles: list[dict], args: argparse.Namespace) -> dict[str, object]:
    start = parse_ts(args.window_start)
    end = parse_ts(args.window_end)
    strategy = StrategyConfig(
        instrument=args.instrument,
        fast_window=args.fast_window,
        slow_window=args.slow_window,
        units=args.max_units,
        risk_per_trade_fraction=getattr(args, "risk_per_trade_fraction", 0.0025),
        long_score_threshold=getattr(args, "long_score_threshold", 2.25),
        short_score_threshold=getattr(args, "short_score_threshold", 2.0),
        regime_score_threshold=getattr(args, "regime_score_threshold", 1.0),
        trailing_atr_multiple=getattr(args, "trailing_atr_multiple", 1.25),
        break_even_atr_multiple=getattr(args, "break_even_atr_multiple", 1.0),
        max_hold_candles=getattr(args, "max_hold_candles", 24),
    )
    policy = RiskPolicy(
        practice_only=True,
        allowed_instruments=(args.instrument,),
        max_units_per_trade=args.max_units,
        max_open_trades=args.max_open_trades,
    )
    health_cfg = HealthConfig(
        min_candles=args.slow_window,
        max_staleness_seconds=10**9,
        max_failures=3,
        min_atr=0.0,
        max_daily_loss=10**9,
        max_weekly_loss=10**9,
        min_regime_score=getattr(args, "regime_score_threshold", 1.0),
        allowed_hours_utc=tuple(
            int(x)
            for x in getattr(args, "allowed_hours_utc", "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23").split(",")
            if str(x).strip() != ""
        ),
    )

    replay_rows: list[dict[str, object]] = []
    simulated_position = 0
    simulated_trade_count = 0
    open_trade: dict[str, object] | None = None
    completed_trades: list[dict[str, object]] = []
    action_counts = {"buy": 0, "sell": 0, "close": 0, "hold": 0}
    equity_curve: list[dict[str, object]] = []
    running_gross_pnl = 0.0

    for idx, candle in enumerate(candles):
        candle_time = parse_ts(candle["time"])
        in_window = start <= candle_time <= end
        history = candles[: idx + 1]
        snapshot = AccountSnapshot(
            environment="practice",
            account_id="historical-replay",
            nav=100000.0,
            balance=100000.0,
            open_trade_count=1 if simulated_position != 0 else 0,
            positions_by_instrument={args.instrument: simulated_position},
        )
        action = moving_average_crossover(history, strategy, snapshot)
        latest_atr = None
        try:
            latest_atr = atr(history, strategy.atr_period)
        except ValueError:
            pass
        if in_window and open_trade is not None:
            update_trade_excursions(open_trade, float((candle.get("mid") or {}).get("c")))
            managed_action = managed_exit_action(
                trade=open_trade,
                candle_time=candle["time"],
                latest_close=float((candle.get("mid") or {}).get("c")),
                latest_atr=latest_atr,
                strategy=strategy,
                granularity=args.granularity,
            )
            if managed_action is not None:
                action = managed_action
        health = evaluate_bot_health(
            candles=history,
            snapshot=snapshot,
            action=action,
            policy=policy,
            failure_count=0,
            config=health_cfg,
            latest_atr=latest_atr,
            daily_pnl=0.0,
            weekly_pnl=0.0,
            regime_score=float(action.metadata.get("regime_score")) if action.metadata and action.metadata.get("regime_score") is not None else None,
        )

        row = {
            "time": candle["time"],
            "close": float((candle.get("mid") or {}).get("c")),
            "action": action.action,
            "reason": action.reason,
            "health_ok": health.ok,
            "health_reasons": health.reasons,
            "position_before": simulated_position,
        }

        if in_window and health.ok:
            if action.action == "buy" and simulated_position == 0:
                simulated_position = action.units
                simulated_trade_count += 1
                open_trade = {
                    "side": "long",
                    "entry_time": candle["time"],
                    "entry_price": row["close"],
                    "units": action.units,
                    "setup_reason": action.reason,
                    "max_favorable_price": row["close"],
                    "max_adverse_price": row["close"],
                    "peak_price": row["close"],
                    "trough_price": row["close"],
                    "opened_at_time": candle["time"],
                }
            elif action.action == "sell" and simulated_position == 0:
                simulated_position = -action.units
                simulated_trade_count += 1
                open_trade = {
                    "side": "short",
                    "entry_time": candle["time"],
                    "entry_price": row["close"],
                    "units": action.units,
                    "setup_reason": action.reason,
                    "max_favorable_price": row["close"],
                    "max_adverse_price": row["close"],
                    "peak_price": row["close"],
                    "trough_price": row["close"],
                    "opened_at_time": candle["time"],
                }
            elif action.action == "close" and simulated_position != 0:
                if open_trade is not None:
                    completed_trades.append(
                        close_trade(
                            open_trade,
                            candle["time"],
                            row["close"],
                            forced=False,
                            exit_reason=action.reason,
                            spread_pips=getattr(args, "spread_pips", 0.00008),
                            slippage_pips=getattr(args, "slippage_pips", 0.00002),
                        )
                    )
                    running_gross_pnl = sum(float(t["net_pnl"]) for t in completed_trades)
                simulated_position = 0
                simulated_trade_count += 1
                open_trade = None
            action_counts[action.action] += 1
            row["executed"] = action.action in {"buy", "sell", "close"}
        else:
            row["executed"] = False
            if in_window:
                action_counts[action.action] += 1

        row["position_after"] = simulated_position
        row["equity_net_pnl"] = running_gross_pnl

        if in_window:
            replay_rows.append(row)
            equity_curve.append({"time": row["time"], "net_pnl": running_gross_pnl})

    if open_trade is not None and replay_rows:
        completed_trades.append(
            close_trade(
                open_trade,
                replay_rows[-1]["time"],
                replay_rows[-1]["close"],
                forced=True,
                exit_reason="forced_window_end",
                spread_pips=getattr(args, "spread_pips", 0.00008),
                slippage_pips=getattr(args, "slippage_pips", 0.00002),
            )
        )
        running_gross_pnl = sum(float(t["net_pnl"]) for t in completed_trades)
        equity_curve.append({"time": replay_rows[-1]["time"], "net_pnl": running_gross_pnl})

    return {
        "window_rows": replay_rows,
        "action_counts": action_counts,
        "ending_position": simulated_position,
        "simulated_trade_events": simulated_trade_count,
        "completed_trades": completed_trades,
        "summary": summarize_trades(completed_trades),
        "equity_curve": equity_curve,
        "setup_summary": summarize_setups(completed_trades),
    }


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def update_trade_excursions(trade: dict[str, object], price: float) -> None:
    side = trade["side"]
    max_favorable = float(trade["max_favorable_price"])
    max_adverse = float(trade["max_adverse_price"])
    peak = float(trade.get("peak_price", price))
    trough = float(trade.get("trough_price", price))
    if side == "long":
        trade["max_favorable_price"] = max(max_favorable, price)
        trade["max_adverse_price"] = min(max_adverse, price)
        trade["peak_price"] = max(peak, price)
        trade["trough_price"] = min(trough, price)
    else:
        trade["max_favorable_price"] = min(max_favorable, price)
        trade["max_adverse_price"] = max(max_adverse, price)
        trade["peak_price"] = min(peak, price)
        trade["trough_price"] = max(trough, price)


def close_trade(
    trade: dict[str, object],
    exit_time: str,
    exit_price: float,
    *,
    forced: bool,
    exit_reason: str,
    spread_pips: float,
    slippage_pips: float,
) -> dict[str, object]:
    entry_price = float(trade["entry_price"])
    side = str(trade["side"])
    units = int(trade["units"])
    if side == "long":
        pnl_per_unit = exit_price - entry_price
        mfe = float(trade["max_favorable_price"]) - entry_price
        mae = float(trade["max_adverse_price"]) - entry_price
    else:
        pnl_per_unit = entry_price - exit_price
        mfe = entry_price - float(trade["max_favorable_price"])
        mae = entry_price - float(trade["max_adverse_price"])
    gross_pnl = pnl_per_unit * units
    cost_per_unit = spread_pips + slippage_pips
    total_cost = cost_per_unit * units
    net_pnl = gross_pnl - total_cost
    return {
        **trade,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "forced_exit": forced,
        "exit_reason": exit_reason,
        "pnl_per_unit": pnl_per_unit,
        "gross_pnl": gross_pnl,
        "cost_per_unit": cost_per_unit,
        "total_cost": total_cost,
        "net_pnl": net_pnl,
        "mfe_per_unit": mfe,
        "mae_per_unit": mae,
    }


def summarize_trades(trades: list[dict[str, object]]) -> dict[str, object]:
    if not trades:
        return {
            "trade_count": 0,
            "gross_pnl": 0.0,
            "net_pnl": 0.0,
            "wins": 0,
            "losses": 0,
            "avg_pnl_per_trade": 0.0,
            "avg_net_pnl_per_trade": 0.0,
            "win_rate": 0.0,
            "expectancy": 0.0,
            "max_drawdown": 0.0,
        }
    gross_pnl = sum(float(t["gross_pnl"]) for t in trades)
    net_pnl = sum(float(t["net_pnl"]) for t in trades)
    wins = sum(1 for t in trades if float(t["net_pnl"]) > 0)
    losses = sum(1 for t in trades if float(t["net_pnl"]) < 0)
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for trade in trades:
        equity += float(trade["net_pnl"])
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    return {
        "trade_count": len(trades),
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "wins": wins,
        "losses": losses,
        "avg_pnl_per_trade": gross_pnl / len(trades),
        "avg_net_pnl_per_trade": net_pnl / len(trades),
        "win_rate": wins / len(trades),
        "expectancy": net_pnl / len(trades),
        "max_drawdown": max_drawdown,
    }


def summarize_setups(trades: list[dict[str, object]]) -> dict[str, object]:
    grouped: dict[str, dict[str, float]] = {}
    for trade in trades:
        key = str(trade.get("setup_reason") or "unknown")
        row = grouped.setdefault(
            key,
            {"trade_count": 0, "wins": 0, "losses": 0, "net_pnl": 0.0},
        )
        row["trade_count"] += 1
        net = float(trade.get("net_pnl", 0.0))
        row["net_pnl"] += net
        if net > 0:
            row["wins"] += 1
        elif net < 0:
            row["losses"] += 1
    for key, row in grouped.items():
        count = row["trade_count"] or 1
        row["win_rate"] = row["wins"] / count
        row["expectancy"] = row["net_pnl"] / count
    return grouped


def managed_exit_action(
    *,
    trade: dict[str, object],
    candle_time: str,
    latest_close: float,
    latest_atr: float | None,
    strategy: StrategyConfig,
    granularity: str,
) -> object | None:
    if latest_atr is None:
        return None
    side = str(trade["side"])
    entry_price = float(trade["entry_price"])
    peak = float(trade.get("peak_price", latest_close))
    trough = float(trade.get("trough_price", latest_close))
    if side == "long":
        if (
            peak - entry_price >= latest_atr * strategy.break_even_atr_multiple
            and latest_close <= entry_price
        ):
            return close_action(args_instrument=strategy.instrument, reason="long_break_even_exit", reference=entry_price)
        trailing_stop = peak - (latest_atr * strategy.trailing_atr_multiple)
        if latest_close <= trailing_stop:
            return close_action(args_instrument=strategy.instrument, reason="long_trailing_exit", reference=trailing_stop)
    else:
        if (
            entry_price - trough >= latest_atr * strategy.break_even_atr_multiple
            and latest_close >= entry_price
        ):
            return close_action(args_instrument=strategy.instrument, reason="short_break_even_exit", reference=entry_price)
        trailing_stop = trough + (latest_atr * strategy.trailing_atr_multiple)
        if latest_close >= trailing_stop:
            return close_action(args_instrument=strategy.instrument, reason="short_trailing_exit", reference=trailing_stop)
    if held_candles(trade, candle_time, granularity) >= strategy.max_hold_candles:
        return close_action(args_instrument=strategy.instrument, reason="max_hold_exit", reference=latest_close)
    return None


def close_action(*, args_instrument: str, reason: str, reference: float):
    return TradeAction(
        action="close",
        instrument=args_instrument,
        confidence=0.7,
        reason=reason,
        metadata={"managed_exit_reference": reference},
    )


def held_candles(trade: dict[str, object], candle_time: str, granularity: str) -> int:
    try:
        current = parse_ts(candle_time)
        opened = parse_ts(str(trade.get("opened_at_time") or candle_time))
    except ValueError:
        return 0
    minutes = max(0.0, (current - opened).total_seconds() / 60.0)
    return int(minutes / max(1, granularity_minutes(granularity)))


def granularity_minutes(value: str) -> int:
    upper = value.upper()
    if upper.startswith("M"):
        return max(1, int(upper[1:]))
    if upper.startswith("H"):
        return max(1, int(upper[1:])) * 60
    if upper == "D":
        return 24 * 60
    return 5


if __name__ == "__main__":
    main()
