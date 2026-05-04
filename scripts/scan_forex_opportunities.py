from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from oanda_autotrader.app import build_account_client, build_instruments_client
from oanda_autotrader.config import (
    load_account_groups_or_default,
    resolve_account_credentials,
    select_account,
)
from oanda_autotrader.execution import (
    PracticeExecutionEngine,
    RiskPolicy,
    TradeAction,
    snapshot_from_account_payload,
)
from oanda_autotrader.indicators import atr
from oanda_autotrader.strategy import StrategyConfig, moving_average_crossover


FX_PAIR_RE = re.compile(r"^[A-Z]{3}_[A-Z]{3}$")
FX_CODES = {
    "AUD",
    "CAD",
    "CHF",
    "CNH",
    "CZK",
    "DKK",
    "EUR",
    "GBP",
    "HKD",
    "HUF",
    "ILS",
    "JPY",
    "MXN",
    "NOK",
    "NZD",
    "PLN",
    "SEK",
    "SGD",
    "THB",
    "TRY",
    "USD",
    "ZAR",
    "BRL",
    "CLP",
    "COP",
    "INR",
    "KRW",
    "MYR",
    "PHP",
    "RON",
    "SAR",
    "TWD",
    "AED",
    "QAR",
    "KWD",
    "BHD",
    "RUB",
    "CNY",
    "NZD",
    "TRY",
}

LIQUID_FX_PAIRS = {
    "AUD_CAD",
    "AUD_CHF",
    "AUD_JPY",
    "AUD_NZD",
    "AUD_USD",
    "CAD_CHF",
    "CAD_JPY",
    "EUR_AUD",
    "EUR_CAD",
    "EUR_CHF",
    "EUR_GBP",
    "EUR_JPY",
    "EUR_NZD",
    "EUR_USD",
    "GBP_AUD",
    "GBP_CAD",
    "GBP_CHF",
    "GBP_JPY",
    "GBP_NZD",
    "GBP_USD",
    "NZD_CAD",
    "NZD_CHF",
    "NZD_JPY",
    "NZD_USD",
    "USD_CAD",
    "USD_CHF",
    "USD_JPY",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan tradeable FX pairs and rank opportunities.")
    parser.add_argument("--accounts-path", default="accounts.yaml")
    parser.add_argument("--group", default="demo")
    parser.add_argument("--account", default="Primary")
    parser.add_argument("--granularity", default="M5")
    parser.add_argument("--count", type=int, default=120)
    parser.add_argument("--fast-window", type=int, default=5)
    parser.add_argument("--slow-window", type=int, default=20)
    parser.add_argument("--units", type=int, default=100)
    parser.add_argument("--risk-per-trade-fraction", type=float, default=0.0025)
    parser.add_argument("--long-score-threshold", type=float, default=3.0)
    parser.add_argument("--short-score-threshold", type=float, default=1.75)
    parser.add_argument("--regime-score-threshold", type=float, default=1.25)
    parser.add_argument("--exit-long-score-threshold", type=float, default=2.0)
    parser.add_argument("--exit-short-score-threshold", type=float, default=1.5)
    parser.add_argument("--exit-regime-score-threshold", type=float, default=1.0)
    parser.add_argument("--trailing-atr-multiple", type=float, default=0.75)
    parser.add_argument("--break-even-atr-multiple", type=float, default=0.5)
    parser.add_argument("--max-hold-candles", type=int, default=18)
    parser.add_argument("--exit-trailing-atr-multiple", type=float, default=0.75)
    parser.add_argument("--exit-break-even-atr-multiple", type=float, default=0.5)
    parser.add_argument("--exit-max-hold-candles", type=int, default=18)
    parser.add_argument("--max-open-trades", type=int, default=5)
    parser.add_argument("--max-units", type=int, default=100)
    parser.add_argument("--max-gross-position-units", type=int, default=300)
    parser.add_argument("--max-currency-gross-units", type=int, default=200)
    parser.add_argument("--max-currency-positions", type=int, default=2)
    parser.add_argument("--min-score", type=float, default=0.0)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--output", default="data/forex_opportunity_scan.json")
    parser.add_argument("--include-held", action="store_true")
    parser.add_argument("--majors-only", action="store_true", default=True, help="Limit scanning to the most liquid major FX pairs.")
    parser.add_argument("--submit", action="store_true", help="Submit the best ranked trade if it clears the score threshold.")
    parser.add_argument("--min-submit-score", type=float, default=5.0)
    parser.add_argument("--max-new-trades", type=int, default=5)
    parser.add_argument("--autonomous", action="store_true", help="Keep scanning and acting on a loop.")
    parser.add_argument("--iterations", type=int, default=1, help="Number of autonomous cycles to run. Use 0 for infinite.")
    parser.add_argument("--interval-seconds", type=int, default=60, help="Sleep between autonomous cycles.")
    parser.add_argument("--manage-exits", action="store_true", help="Evaluate and manage open positions before new entries.")
    parser.add_argument("--audit-path", default="data/forex_autonomous_audit.jsonl")
    parser.add_argument("--state-path", default="data/forex_autonomous_state.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.autonomous and args.iterations < 0:
        raise SystemExit("--iterations must be 0 or greater.")
    cycle = 0
    while True:
        cycle += 1
        run_scan_cycle(args, cycle=cycle)
        if not args.autonomous:
            break
        if args.iterations and cycle >= args.iterations:
            break
        time.sleep(max(1, args.interval_seconds))


def run_scan_cycle(args: argparse.Namespace, *, cycle: int) -> None:
    groups = load_account_groups_or_default(args.accounts_path)
    group, entry = select_account(groups, args.group, args.account)
    app_config = resolve_account_credentials(group, entry)
    account_client = build_account_client(app_config)
    instruments_client = build_instruments_client(app_config)

    details = account_client.get_account(app_config.account_id)
    summary = account_client.get_account_summary(app_config.account_id)
    snapshot = snapshot_from_account_payload(app_config, details, summary)
    tradeable = account_client.get_instruments(app_config.account_id).get("instruments", [])
    instruments = [
        str(item.get("name"))
        for item in tradeable
        if isinstance(item, dict)
        and is_fx_pair(str(item.get("name") or ""))
        and (not args.majors_only or is_major_fx_pair(str(item.get("name") or "")))
    ]

    entry_candidates = []
    held = {name for name, units in snapshot.positions_by_instrument.items() if units}
    managed_actions = []
    strategy = StrategyConfig(
        instrument=args.account,  # placeholder; overridden per instrument below
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
    )
    exit_strategy = StrategyConfig(
        instrument=args.account,  # placeholder; overridden per instrument below
        fast_window=args.fast_window,
        slow_window=args.slow_window,
        units=args.max_units,
        min_separation=strategy.min_separation,
        atr_period=strategy.atr_period,
        atr_stop_multiple=strategy.atr_stop_multiple,
        atr_target_multiple=strategy.atr_target_multiple,
        risk_per_trade_fraction=strategy.risk_per_trade_fraction,
        long_score_threshold=args.exit_long_score_threshold,
        short_score_threshold=args.exit_short_score_threshold,
        regime_score_threshold=args.exit_regime_score_threshold,
        trailing_atr_multiple=args.exit_trailing_atr_multiple,
        break_even_atr_multiple=args.exit_break_even_atr_multiple,
        max_hold_candles=args.exit_max_hold_candles,
    )

    for instrument in instruments:
        if not args.include_held and instrument in held:
            continue
        candles_payload = instruments_client.get_candles(
            instrument,
            price="M",
            granularity=args.granularity,
            count=args.count,
        )
        candles = candles_payload.get("candles", [])
        if not candles:
            continue
        inst_strategy = StrategyConfig(
            instrument=instrument,
            fast_window=strategy.fast_window,
            slow_window=strategy.slow_window,
            units=strategy.units,
            min_separation=strategy.min_separation,
            atr_period=strategy.atr_period,
            atr_stop_multiple=strategy.atr_stop_multiple,
            atr_target_multiple=strategy.atr_target_multiple,
            risk_per_trade_fraction=strategy.risk_per_trade_fraction,
            long_score_threshold=strategy.long_score_threshold,
            short_score_threshold=strategy.short_score_threshold,
            regime_score_threshold=strategy.regime_score_threshold,
            trailing_atr_multiple=strategy.trailing_atr_multiple,
            max_hold_candles=strategy.max_hold_candles,
            break_even_atr_multiple=strategy.break_even_atr_multiple,
        )
        action = moving_average_crossover(candles, inst_strategy, snapshot)
        latest_atr = None
        try:
            latest_atr = atr(candles, inst_strategy.atr_period)
        except ValueError:
            pass
        score = opportunity_score(action.action, action.metadata or {}, latest_atr)
        if score < args.min_score:
            continue
        entry_candidates.append(
            {
                "instrument": instrument,
                "action": action.action,
                "kind": "entry",
                "reason": action.reason,
                "score": score,
                "confidence": action.confidence,
                "units": action.units,
                "stop_loss_price": action.stop_loss_price,
                "take_profit_price": action.take_profit_price,
                "metadata": action.metadata,
                "atr": latest_atr,
                "has_position": instrument in held,
            }
        )

    if args.manage_exits and held:
        managed_actions.extend(
            build_managed_exit_candidates(
                app_config=app_config,
                snapshot=snapshot,
                instruments=instruments,
                args=args,
                strategy=exit_strategy,
                instruments_client=instruments_client,
            )
        )

    candidates = managed_actions + entry_candidates

    candidates.sort(key=lambda item: item["score"], reverse=True)
    payload = {
        "account_id": app_config.account_id,
        "group": app_config.group_name,
        "environment": app_config.environment,
        "granularity": args.granularity,
        "scan_count": len(candidates),
        "held_positions": sorted(held),
        "exit_opportunities": managed_actions,
        "entry_opportunities": entry_candidates,
        "long_opportunities": [item for item in entry_candidates if item.get("action") == "buy"],
        "short_opportunities": [item for item in entry_candidates if item.get("action") == "sell"],
        "top_opportunities": candidates[: args.top],
        "submission": None,
    }

    if args.submit:
        submissions = maybe_submit_candidates(
            app_config=app_config,
            snapshot=snapshot,
            candidates=candidates,
            args=args,
        )
        payload["submissions"] = submissions
        payload["submission"] = submissions[0] if submissions else None

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_audit_record(
        Path(args.audit_path),
        cycle=cycle,
        app_config=app_config,
        summary=summary,
        payload=payload,
        snapshot=snapshot,
        candidates=candidates,
    )
    write_state_record(
        Path(args.state_path),
        cycle=cycle,
        app_config=app_config,
        summary=summary,
        payload=payload,
        snapshot=snapshot,
        candidates=candidates,
    )

    print(
        f"cycle {cycle}: scanned {len(instruments)} instruments, found {len(candidates)} opportunities"
    )
    for row in candidates[: args.top]:
        print(
            f"{row['instrument']} | action={row['action']} score={row['score']:.3f} "
            f"reason={row['reason']} confidence={row['confidence']:.2f}"
        )
    if payload.get("submissions"):
        for submission in payload["submissions"]:
            print(
                f"submitted {submission['instrument']} {submission['action']} "
                f"score={submission['score']:.3f} dry_run={submission['dry_run']}"
            )
    elif payload["submission"] is not None:
        submission = payload["submission"]
        print(
            f"submitted {submission['instrument']} {submission['action']} "
            f"score={submission['score']:.3f} dry_run={submission['dry_run']}"
        )
    print(f"wrote {output}")


def opportunity_score(action: str, metadata: dict[str, object], latest_atr: float | None) -> float:
    action = action.lower()
    long_score = float(metadata.get("long_score", 0.0) or 0.0)
    short_score = float(metadata.get("short_score", 0.0) or 0.0)
    regime_score = float(metadata.get("regime_score", 0.0) or 0.0)
    separation = float(metadata.get("separation", 0.0) or 0.0)
    rsi = float(metadata.get("rsi", 50.0) or 50.0)
    atr_bonus = 0.0 if latest_atr is None else min(0.5, latest_atr * 1000.0)

    if action == "buy":
        base = long_score
        momentum = max(0.0, (rsi - 50.0) / 20.0)
    elif action == "sell":
        base = short_score
        momentum = max(0.0, (50.0 - rsi) / 20.0)
    else:
        base = max(long_score, short_score) * 0.25
        momentum = 0.0

    return base + regime_score * 0.5 + momentum + min(0.5, separation * 1000.0) + atr_bonus


def is_fx_pair(name: str) -> bool:
    match = FX_PAIR_RE.match(name or "")
    if not match:
        return False
    base, quote = name.split("_", 1)
    return base in FX_CODES and quote in FX_CODES


def is_major_fx_pair(name: str) -> bool:
    if not is_fx_pair(name):
        return False
    return name in LIQUID_FX_PAIRS


def build_managed_exit_candidates(
    *,
    app_config,
    snapshot,
    instruments: list[str],
    args: argparse.Namespace,
    strategy: StrategyConfig,
    instruments_client,
) -> list[dict[str, object]]:
    managed: list[dict[str, object]] = []
    for instrument, units in snapshot.positions_by_instrument.items():
        if not units:
            continue
        if instrument not in instruments:
            continue
        candles_payload = instruments_client.get_candles(
            instrument,
            price="M",
            granularity=args.granularity,
            count=args.count,
        )
        candles = candles_payload.get("candles", [])
        if not candles:
            continue
        inst_strategy = StrategyConfig(
            instrument=instrument,
            fast_window=strategy.fast_window,
            slow_window=strategy.slow_window,
            units=strategy.units,
            min_separation=strategy.min_separation,
            atr_period=strategy.atr_period,
            atr_stop_multiple=strategy.atr_stop_multiple,
            atr_target_multiple=strategy.atr_target_multiple,
            risk_per_trade_fraction=strategy.risk_per_trade_fraction,
            long_score_threshold=strategy.long_score_threshold,
            short_score_threshold=strategy.short_score_threshold,
            regime_score_threshold=strategy.regime_score_threshold,
            trailing_atr_multiple=strategy.trailing_atr_multiple,
            max_hold_candles=strategy.max_hold_candles,
            break_even_atr_multiple=strategy.break_even_atr_multiple,
        )
        candidate = evaluate_managed_exit(instrument, units, candles, snapshot, inst_strategy)
        if candidate is not None:
            managed.append(candidate)
    return managed


def evaluate_managed_exit(
    instrument: str,
    units: int,
    candles: list[dict],
    snapshot,
    strategy: StrategyConfig,
) -> dict[str, object] | None:
    action = moving_average_crossover(candles, strategy, snapshot)
    latest_atr = None
    try:
        latest_atr = atr(candles, strategy.atr_period)
    except ValueError:
        pass
    if latest_atr is None:
        return None
    metadata = action.metadata or {}
    current_units = int(metadata.get("current_units", units) or units)
    if current_units == 0:
        return None
    action_name = str(action.action).lower()
    if current_units > 0 and action_name == "sell":
        return {
            "instrument": instrument,
            "action": "close",
            "kind": "exit",
            "reason": "managed_close_long",
            "score": opportunity_score("sell", metadata, latest_atr) + 1.0,
            "confidence": 0.75,
            "units": abs(current_units),
            "stop_loss_price": None,
            "take_profit_price": None,
            "metadata": metadata,
            "atr": latest_atr,
            "has_position": True,
            "managed": True,
        }
    if current_units < 0 and action_name == "buy":
        return {
            "instrument": instrument,
            "action": "close",
            "kind": "exit",
            "reason": "managed_close_short",
            "score": opportunity_score("buy", metadata, latest_atr) + 1.0,
            "confidence": 0.75,
            "units": abs(current_units),
            "stop_loss_price": None,
            "take_profit_price": None,
            "metadata": metadata,
            "atr": latest_atr,
            "has_position": True,
            "managed": True,
        }
    if current_units > 0 and metadata.get("long_score", 0.0) < 0.5:
        return {
            "instrument": instrument,
            "action": "close",
            "kind": "exit",
            "reason": "managed_long_decay",
            "score": 1.0,
            "confidence": 0.7,
            "units": abs(current_units),
            "stop_loss_price": None,
            "take_profit_price": None,
            "metadata": metadata,
            "atr": latest_atr,
            "has_position": True,
            "managed": True,
        }
    if current_units < 0 and metadata.get("short_score", 0.0) < 0.5:
        return {
            "instrument": instrument,
            "action": "close",
            "kind": "exit",
            "reason": "managed_short_decay",
            "score": 1.0,
            "confidence": 0.7,
            "units": abs(current_units),
            "stop_loss_price": None,
            "take_profit_price": None,
            "metadata": metadata,
            "atr": latest_atr,
            "has_position": True,
            "managed": True,
        }
    return None


def maybe_submit_best_candidate(
    *,
    app_config,
    snapshot,
    candidates: list[dict[str, object]],
    args: argparse.Namespace,
) -> dict[str, object] | None:
    submissions = maybe_submit_candidates(
        app_config=app_config,
        snapshot=snapshot,
        candidates=candidates,
        args=args,
    )
    return submissions[0] if submissions else None


def maybe_submit_candidates(
    *,
    app_config,
    snapshot,
    candidates: list[dict[str, object]],
    args: argparse.Namespace,
) -> list[dict[str, object]]:
    engine = PracticeExecutionEngine(
        app_config,
        RiskPolicy(
            practice_only=True,
            allowed_instruments=tuple(item["instrument"] for item in candidates) or (),
            max_units_per_trade=args.max_units,
            max_open_trades=args.max_open_trades,
            max_gross_position_units=args.max_gross_position_units,
            max_currency_gross_units=args.max_currency_gross_units,
            max_currency_positions=args.max_currency_positions,
        ),
    )
    ordered_candidates = sorted(
        candidates,
        key=lambda item: (0 if str(item.get("action")) == "close" else 1, -float(item.get("score", 0.0) or 0.0)),
    )
    projected_snapshot = snapshot
    submissions: list[dict[str, object]] = []
    new_entries_submitted = 0
    for candidate in ordered_candidates:
        if float(candidate.get("score", 0.0) or 0.0) < args.min_submit_score:
            continue
        action = build_trade_action(candidate)
        if action.action == "hold":
            continue
        if action.action == "close":
            current_units = int(projected_snapshot.positions_by_instrument.get(action.instrument, 0) or 0)
            if current_units == 0:
                continue
        else:
            if new_entries_submitted >= args.max_new_trades:
                continue
            if int(projected_snapshot.open_trade_count) >= args.max_open_trades:
                continue
            if candidate.get("has_position"):
                continue
            if not can_submit_entry(engine, projected_snapshot, action):
                continue
        try:
            result = engine.execute(action, projected_snapshot, dry_run=app_config.environment != "practice")
        except Exception as exc:  # pragma: no cover - live failure path
            submissions.append({
                "instrument": candidate["instrument"],
                "action": action.action,
                "score": candidate["score"],
                "reason": candidate["reason"],
                "dry_run": app_config.environment != "practice",
                "error": str(exc),
            })
            continue
        submissions.append({
            "instrument": candidate["instrument"],
            "action": action.action,
            "score": candidate["score"],
            "reason": candidate["reason"],
            "dry_run": app_config.environment != "practice",
            "result": result,
        })
        projected_snapshot = engine.project_snapshot(projected_snapshot, action)
        if action.action != "close":
            new_entries_submitted += 1
    return submissions


def can_submit_entry(engine: PracticeExecutionEngine, snapshot, action: TradeAction) -> bool:
    if action.action.lower() not in {"buy", "sell"}:
        return True
    projected = engine.project_snapshot(snapshot, action)
    if projected.open_trade_count > engine.policy.max_open_trades:
        return False
    if engine.projected_gross_position_units(snapshot, action) > engine.policy.max_gross_position_units:
        return False
    if engine.projected_currency_gross_units(snapshot, action) > engine.policy.max_currency_gross_units:
        return False
    if engine.policy.max_currency_positions > 0:
        currency_counts = engine.policy._currency_position_counts(projected.positions_by_instrument)
        if max(currency_counts.values(), default=0) > engine.policy.max_currency_positions:
            return False
    return True


def build_trade_action(candidate: dict[str, object]):
    action = str(candidate["action"])
    if action == "close":
        return TradeAction(
            action="close",
            instrument=str(candidate["instrument"]),
            units=int(candidate.get("units") or 0),
            confidence=float(candidate.get("confidence", 0.0) or 0.0),
            reason=str(candidate.get("reason") or "managed_exit"),
            metadata=dict(candidate.get("metadata") or {}),
        )
    if action not in {"buy", "sell"}:
        return TradeAction(action="hold", instrument=str(candidate["instrument"]))
    return TradeAction(
        action=action,
        instrument=str(candidate["instrument"]),
        units=int(candidate.get("units") or 0),
        confidence=float(candidate.get("confidence", 0.0) or 0.0),
        reason=str(candidate.get("reason") or "scanner_pick"),
        stop_loss_price=str(candidate.get("stop_loss_price")) if candidate.get("stop_loss_price") else None,
        take_profit_price=str(candidate.get("take_profit_price")) if candidate.get("take_profit_price") else None,
        metadata=dict(candidate.get("metadata") or {}),
    )


def write_audit_record(
    path: Path,
    *,
    cycle: int,
    app_config,
    summary,
    payload: dict[str, object],
    snapshot,
    candidates: list[dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    top = candidates[0] if candidates else {}
    submission = payload.get("submission") or {}
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cycle": cycle,
        "account_id": app_config.account_id,
        "group": app_config.group_name,
        "instrument": top.get("instrument") or submission.get("instrument") or "multi",
        "granularity": payload.get("granularity"),
        "environment": app_config.environment,
        "dry_run": app_config.environment != "practice",
        "blocked": [],
        "health": {"ok": True, "reasons": [], "details": {}},
        "action": submission or top,
        "result": submission.get("result") if isinstance(submission, dict) else None,
        "account_summary": _compact_account_summary(summary),
        "snapshot": {
            "nav": snapshot.nav,
            "balance": snapshot.balance,
            "open_trade_count": snapshot.open_trade_count,
            "positions_by_instrument": snapshot.positions_by_instrument,
        },
        "candidates": candidates[:10],
        "submission": submission or None,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def write_state_record(
    path: Path,
    *,
    cycle: int,
    app_config,
    summary,
    payload: dict[str, object],
    snapshot,
    candidates: list[dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_state = {}
    if path.exists():
        try:
            previous_state = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            previous_state = {}
    account_summary = _compact_account_summary(summary)
    balance = account_summary.get("balance")
    nav = account_summary.get("nav")
    session_start_balance = previous_state.get("session_start_balance", balance)
    session_start_nav = previous_state.get("session_start_nav", nav)
    realized_pnl_session = None
    if balance is not None and session_start_balance is not None:
        realized_pnl_session = float(balance) - float(session_start_balance)
    unrealized_pnl = None
    if nav is not None and balance is not None:
        unrealized_pnl = float(nav) - float(balance)
    active_positions = {name: units for name, units in snapshot.positions_by_instrument.items() if units}
    current_position = _compact_current_position(active_positions)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cycle": cycle,
        "group": app_config.group_name,
        "environment": app_config.environment,
        "last_action": (payload.get("submission") or {}).get("action")
        if isinstance(payload.get("submission"), dict)
        else "watching",
        "consecutive_failures": 0,
        "current_position": current_position,
        "realized_pnl_day": realized_pnl_session if realized_pnl_session is not None else 0.0,
        "realized_pnl_week": realized_pnl_session if realized_pnl_session is not None else 0.0,
        "unrealized_pnl": unrealized_pnl if unrealized_pnl is not None else 0.0,
        "session_start_balance": session_start_balance,
        "session_start_nav": session_start_nav,
        "open_trade_count": snapshot.open_trade_count,
        "positions_by_instrument": snapshot.positions_by_instrument,
        "active_positions": [
            {"instrument": name, "units": units, "side": "long" if units > 0 else "short"}
            for name, units in sorted(active_positions.items())
        ],
        "latest_candidates": candidates[:10],
        "snapshot": {
            "nav": snapshot.nav,
            "balance": snapshot.balance,
            "open_trade_count": snapshot.open_trade_count,
            "positions_by_instrument": snapshot.positions_by_instrument,
        },
        "submission": payload.get("submission"),
    }
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")


def _compact_account_summary(summary) -> dict[str, object]:
    if summary is None:
        return {}
    account = summary.get("account", {}) if isinstance(summary, dict) else {}
    return {
        "balance": _safe_number(account.get("balance")),
        "nav": _safe_number(account.get("NAV") or account.get("nav")),
        "open_trade_count": _safe_number(account.get("openTradeCount")),
    }


def _compact_current_position(active_positions: dict[str, int]) -> dict[str, object] | None:
    if not active_positions:
        return None
    if len(active_positions) == 1:
        instrument, units = next(iter(active_positions.items()))
        return {
            "instrument": instrument,
            "side": "long" if units > 0 else "short",
            "units": abs(units),
            "entry_price": None,
            "peak_price": None,
            "trough_price": None,
        }
    return {
        "instrument": "multiple",
        "side": "mixed",
        "units": sum(abs(units) for units in active_positions.values()),
        "entry_price": None,
        "peak_price": None,
        "trough_price": None,
    }


def _safe_number(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    main()
