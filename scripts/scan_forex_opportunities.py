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
    parser.add_argument("--majors-only", action="store_true", help="Limit scanning to the most liquid major FX pairs.")
    parser.add_argument("--submit", action="store_true", help="Submit the best ranked trade if it clears the score threshold.")
    parser.add_argument("--min-submit-score", type=float, default=5.4)
    parser.add_argument("--non-liquid-min-submit-score", type=float, default=6.2)
    parser.add_argument("--allow-non-liquid-trades", action="store_true")
    parser.add_argument("--max-new-trades", type=int, default=5)
    parser.add_argument("--max-trades-per-hour", type=int, default=2)
    parser.add_argument("--instrument-cooldown-minutes", type=int, default=180)
    parser.add_argument("--currency-cooldown-minutes", type=int, default=60)
    parser.add_argument("--max-session-loss", type=float, default=1.0)
    parser.add_argument("--disable-adaptive-quality", action="store_true")
    parser.add_argument("--adaptive-min-atr-ratio", type=float, default=0.00012)
    parser.add_argument("--adaptive-recovery-atr-ratio", type=float, default=0.00035)
    parser.add_argument("--adaptive-max-avg-loss", type=float, default=0.08)
    parser.add_argument("--adaptive-max-avg-half-spread-cost", type=float, default=0.08)
    parser.add_argument("--adaptive-max-penalty", type=float, default=1.2)
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
        try:
            run_scan_cycle(args, cycle=cycle)
        except Exception as exc:
            if not args.autonomous:
                raise
            write_cycle_error(Path(args.audit_path), Path(args.state_path), cycle=cycle, error=describe_exception(exc))
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
    instruments = select_scan_instruments(tradeable, majors_only=args.majors_only)
    price_precisions = instrument_price_precisions(tradeable)
    state = load_state_file(Path(args.state_path))
    instrument_quality = state.get("instrument_quality") or {}

    entry_candidates = []
    held = {name for name, units in snapshot.positions_by_instrument.items() if units}
    managed_actions = []
    scan_errors = []
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
        candles_payload = fetch_candles_safe(
            instruments_client,
            instrument,
            granularity=args.granularity,
            count=args.count,
            errors=scan_errors,
        )
        if candles_payload is None:
            continue
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
            price_precision=price_precisions.get(instrument),
        )
        action = moving_average_crossover(candles, inst_strategy, snapshot)
        latest_atr = None
        try:
            latest_atr = atr(candles, inst_strategy.atr_period)
        except ValueError:
            pass
        latest_close = latest_candle_close(candles)
        score = opportunity_score(action.action, action.metadata or {}, latest_atr)
        score, quality = apply_adaptive_quality(
            instrument=instrument,
            score=score,
            latest_atr=latest_atr,
            latest_price=latest_close,
            instrument_quality=instrument_quality,
            args=args,
        )
        if score < args.min_score:
            continue
        metadata = dict(action.metadata or {})
        metadata["atr_ratio"] = quality.get("atr_ratio")
        metadata["quality_penalty"] = quality.get("penalty")
        metadata["quality_reasons"] = quality.get("reasons")
        entry_candidates.append(
            {
                "instrument": instrument,
                "action": action.action,
                "kind": "entry",
                "reason": action.reason,
                "score": score,
                "raw_score": quality.get("raw_score", score),
                "confidence": action.confidence,
                "units": action.units,
                "stop_loss_price": action.stop_loss_price,
                "take_profit_price": action.take_profit_price,
                "metadata": metadata,
                "atr": latest_atr,
                "atr_ratio": quality.get("atr_ratio"),
                "quality_penalty": quality.get("penalty"),
                "quality_reasons": quality.get("reasons"),
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
                price_precisions=price_precisions,
                instruments_client=instruments_client,
                scan_errors=scan_errors,
            )
        )

    candidates = managed_actions + entry_candidates

    candidates.sort(key=lambda item: item["score"], reverse=True)
    payload = {
        "account_id": app_config.account_id,
        "group": app_config.group_name,
        "environment": app_config.environment,
        "granularity": args.granularity,
        "instrument_scope": "liquid_fx" if args.majors_only else "all_fx",
        "instrument_count": len(instruments),
        "scan_count": len(candidates),
        "held_positions": sorted(held),
        "exit_opportunities": managed_actions,
        "entry_opportunities": entry_candidates,
        "long_opportunities": rank_directional_watchlist(entry_candidates, "long_score"),
        "short_opportunities": rank_directional_watchlist(entry_candidates, "short_score"),
        "scan_errors": scan_errors,
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
        payload["decision_summary"] = build_decision_summary(candidates, submissions, args)

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


def latest_candle_close(candles: list[dict]) -> float | None:
    if not candles:
        return None
    try:
        return float((candles[-1].get("mid") or {}).get("c"))
    except (TypeError, ValueError, AttributeError):
        return None


def apply_adaptive_quality(
    *,
    instrument: str,
    score: float,
    latest_atr: float | None,
    latest_price: float | None,
    instrument_quality: dict[str, object],
    args: argparse.Namespace,
) -> tuple[float, dict[str, object]]:
    raw_score = float(score)
    if bool(getattr(args, "disable_adaptive_quality", False)):
        return raw_score, {"raw_score": raw_score, "penalty": 0.0, "reasons": [], "atr_ratio": None}

    atr_ratio = None
    if latest_atr is not None and latest_price and latest_price > 0:
        atr_ratio = float(latest_atr) / float(latest_price)

    penalty = 0.0
    reasons: list[str] = []
    min_atr_ratio = float(getattr(args, "adaptive_min_atr_ratio", 0.0) or 0.0)
    if atr_ratio is not None and min_atr_ratio > 0 and atr_ratio < min_atr_ratio:
        penalty += min(0.5, (min_atr_ratio - atr_ratio) / min_atr_ratio * 0.5)
        reasons.append("low_atr")

    stats = instrument_quality.get(instrument) if isinstance(instrument_quality, dict) else None
    if isinstance(stats, dict):
        closed_count = float(stats.get("closed_count", 0) or 0)
        net_pl = float(stats.get("net_pl", 0.0) or 0.0)
        avg_pl = net_pl / closed_count if closed_count else 0.0
        max_avg_loss = abs(float(getattr(args, "adaptive_max_avg_loss", 0.0) or 0.0))
        if closed_count >= 1.5 and avg_pl < -max_avg_loss:
            penalty += min(0.5, abs(avg_pl) / max(max_avg_loss, 1e-9) * 0.25)
            reasons.append("negative_recent_pl")

        fill_count = float(stats.get("fill_count", 0) or 0)
        half_spread_cost = float(stats.get("half_spread_cost", 0.0) or 0.0)
        avg_half_spread = half_spread_cost / fill_count if fill_count else 0.0
        max_half_spread = abs(float(getattr(args, "adaptive_max_avg_half_spread_cost", 0.0) or 0.0))
        if fill_count >= 1.5 and max_half_spread > 0 and avg_half_spread > max_half_spread:
            penalty += min(0.5, avg_half_spread / max_half_spread * 0.2)
            reasons.append("high_spread_cost")

    recovery_atr_ratio = float(getattr(args, "adaptive_recovery_atr_ratio", 0.0) or 0.0)
    if penalty > 0 and atr_ratio is not None and recovery_atr_ratio > 0 and atr_ratio >= recovery_atr_ratio:
        penalty *= 0.35
        reasons.append("atr_recovery")

    max_penalty = float(getattr(args, "adaptive_max_penalty", 1.2) or 1.2)
    penalty = min(max_penalty, penalty)
    return max(0.0, raw_score - penalty), {
        "raw_score": raw_score,
        "penalty": penalty,
        "reasons": reasons,
        "atr_ratio": atr_ratio,
    }


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


def select_scan_instruments(tradeable: list[dict[str, object]], *, majors_only: bool) -> list[str]:
    instruments = {
        str(item.get("name"))
        for item in tradeable
        if isinstance(item, dict) and is_fx_pair(str(item.get("name") or ""))
    }
    if majors_only:
        instruments = {name for name in instruments if is_major_fx_pair(name)}
    return sorted(instruments)


def instrument_price_precisions(tradeable: list[dict[str, object]]) -> dict[str, int]:
    precisions: dict[str, int] = {}
    for item in tradeable:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if not is_fx_pair(name):
            continue
        try:
            precisions[name] = int(item.get("displayPrecision"))
        except (TypeError, ValueError):
            continue
    return precisions


def rank_directional_watchlist(candidates: list[dict[str, object]], score_key: str) -> list[dict[str, object]]:
    return sorted(
        candidates,
        key=lambda item: (
            float((item.get("metadata") or {}).get(score_key, 0.0) or 0.0),
            float(item.get("score", 0.0) or 0.0),
        ),
        reverse=True,
    )


def fetch_candles_safe(
    instruments_client,
    instrument: str,
    *,
    granularity: str,
    count: int,
    errors: list[dict[str, object]] | None = None,
) -> dict[str, object] | None:
    try:
        return instruments_client.get_candles(
            instrument,
            price="M",
            granularity=granularity,
            count=count,
        )
    except Exception as exc:
        if errors is not None:
            errors.append(
                {
                    "instrument": instrument,
                    "stage": "candles",
                    "error": describe_exception(exc),
                }
            )
        return None


def build_managed_exit_candidates(
    *,
    app_config,
    snapshot,
    instruments: list[str],
    args: argparse.Namespace,
    strategy: StrategyConfig,
    price_precisions: dict[str, int] | None,
    instruments_client,
    scan_errors: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    managed: list[dict[str, object]] = []
    for instrument, units in snapshot.positions_by_instrument.items():
        if not units:
            continue
        if instrument not in instruments:
            continue
        candles_payload = fetch_candles_safe(
            instruments_client,
            instrument,
            granularity=args.granularity,
            count=args.count,
            errors=scan_errors,
        )
        if candles_payload is None:
            continue
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
            price_precision=(price_precisions or {}).get(instrument),
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
    state = load_state_file(Path(args.state_path))
    recent_entries = list(state.get("recent_entries") or [])
    realized_pnl_day = float(state.get("realized_pnl_day", 0.0) or 0.0)
    for candidate in ordered_candidates:
        candidate_action = str(candidate.get("action") or "").lower()
        candidate_score = float(candidate.get("score", 0.0) or 0.0)
        required_score = required_submit_score(str(candidate.get("instrument") or ""), args)
        if candidate_action != "close" and non_liquid_trade_blocked(str(candidate.get("instrument") or ""), args):
            candidate["required_score"] = required_score
            candidate["blocked_reason"] = "non_liquid_trade_disabled"
            continue
        if candidate_action != "close" and candidate_score < required_score:
            candidate["required_score"] = required_score
            candidate["blocked_reason"] = "below_submit_threshold"
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
            throttle_reason = entry_throttle_reason(
                action,
                recent_entries,
                args,
                realized_pnl_day=realized_pnl_day,
            )
            if throttle_reason:
                candidate["blocked_reason"] = throttle_reason
                continue
            if not can_submit_entry(engine, projected_snapshot, action):
                candidate["blocked_reason"] = "risk_policy"
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
                "error": describe_exception(exc),
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
        executed = bool(result.get("submitted")) or bool(result.get("dry_run"))
        if not executed:
            continue
        projected_snapshot = engine.project_snapshot(projected_snapshot, action)
        if action.action != "close":
            new_entries_submitted += 1
            recent_entries.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "instrument": action.instrument,
                    "action": action.action,
                    "units": action.units,
                }
            )
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


def build_decision_summary(
    candidates: list[dict[str, object]],
    submissions: list[dict[str, object]],
    args: argparse.Namespace,
) -> dict[str, object]:
    submitted = [item for item in submissions if (item.get("result") or {}).get("submitted")]
    if submitted:
        return {
            "decision": "submitted",
            "reason": "execution_submitted",
            "submitted_count": len(submitted),
            "instruments": [item.get("instrument") for item in submitted],
            "min_submit_score": args.min_submit_score,
            "non_liquid_min_submit_score": getattr(args, "non_liquid_min_submit_score", None),
            "allow_non_liquid_trades": bool(getattr(args, "allow_non_liquid_trades", False)),
        }

    actionable = [
        item
        for item in candidates
        if str(item.get("action") or "").lower() in {"buy", "sell", "close"}
    ]
    if not actionable:
        top = max(candidates, key=lambda item: float(item.get("score", 0.0) or 0.0), default=None)
        summary = {
            "decision": "watching",
            "reason": "no_actionable_candidates",
            "submitted_count": 0,
            "min_submit_score": args.min_submit_score,
            "non_liquid_min_submit_score": getattr(args, "non_liquid_min_submit_score", None),
            "allow_non_liquid_trades": bool(getattr(args, "allow_non_liquid_trades", False)),
        }
        if top:
            summary.update(
                {
                    "instrument": top.get("instrument"),
                    "action": top.get("action"),
                    "score": float(top.get("score", 0.0) or 0.0),
                    "filter_reason": top.get("reason"),
                    "long_score": (top.get("metadata") or {}).get("long_score"),
                    "short_score": (top.get("metadata") or {}).get("short_score"),
                    "regime_score": (top.get("metadata") or {}).get("regime_score"),
                    "rsi": (top.get("metadata") or {}).get("rsi"),
                }
            )
        return summary

    top = max(actionable, key=lambda item: float(item.get("score", 0.0) or 0.0))
    top_score = float(top.get("score", 0.0) or 0.0)
    required_score = required_submit_score(str(top.get("instrument") or ""), args)
    metadata = top.get("metadata") or {}
    if non_liquid_trade_blocked(str(top.get("instrument") or ""), args):
        reason = "non_liquid_trade_disabled"
    elif top_score < required_score:
        reason = "below_submit_threshold"
    else:
        reason = str(top.get("blocked_reason") or "not_selected")
    return {
        "decision": "watching",
        "reason": reason,
        "submitted_count": 0,
        "instrument": top.get("instrument"),
        "action": top.get("action"),
        "filter_reason": top.get("reason"),
        "score": top_score,
        "score_gap": max(0.0, required_score - top_score),
        "required_score": required_score,
        "min_submit_score": args.min_submit_score,
        "non_liquid_min_submit_score": getattr(args, "non_liquid_min_submit_score", None),
        "allow_non_liquid_trades": bool(getattr(args, "allow_non_liquid_trades", False)),
        "long_score": metadata.get("long_score"),
        "short_score": metadata.get("short_score"),
        "regime_score": metadata.get("regime_score"),
        "rsi": metadata.get("rsi"),
        "fib_retracement": metadata.get("fib_retracement"),
    }


def required_submit_score(instrument: str, args: argparse.Namespace) -> float:
    if is_major_fx_pair(instrument):
        return float(getattr(args, "min_submit_score", 0.0) or 0.0)
    return float(
        getattr(
            args,
            "non_liquid_min_submit_score",
            getattr(args, "min_submit_score", 0.0),
        )
        or 0.0
    )


def non_liquid_trade_blocked(instrument: str, args: argparse.Namespace) -> bool:
    return not is_major_fx_pair(instrument) and not bool(getattr(args, "allow_non_liquid_trades", False))


def entry_throttle_reason(
    action: TradeAction,
    recent_entries: list[dict[str, object]],
    args: argparse.Namespace,
    *,
    realized_pnl_day: float,
) -> str | None:
    if action.action.lower() not in {"buy", "sell"}:
        return None
    if realized_pnl_day <= -abs(float(getattr(args, "max_session_loss", 0.0) or 0.0)):
        return "session_loss_limit"

    now = datetime.now(timezone.utc)
    active_entries = [
        entry for entry in recent_entries if entry_age_minutes(entry, now) is not None
    ]
    one_hour_entries = [
        entry for entry in active_entries if (entry_age_minutes(entry, now) or 0.0) <= 60.0
    ]
    max_trades_per_hour = int(getattr(args, "max_trades_per_hour", 0) or 0)
    if max_trades_per_hour > 0 and len(one_hour_entries) >= max_trades_per_hour:
        return "max_trades_per_hour"

    instrument_cooldown = int(getattr(args, "instrument_cooldown_minutes", 0) or 0)
    if instrument_cooldown > 0:
        for entry in active_entries:
            if entry.get("instrument") == action.instrument and (entry_age_minutes(entry, now) or 0.0) < instrument_cooldown:
                return "instrument_cooldown"

    currency_cooldown = int(getattr(args, "currency_cooldown_minutes", 0) or 0)
    action_currencies = set(instrument_currencies(action.instrument) or ())
    if currency_cooldown > 0 and action_currencies:
        for entry in active_entries:
            entry_currencies = set(instrument_currencies(str(entry.get("instrument") or "")) or ())
            if action_currencies & entry_currencies and (entry_age_minutes(entry, now) or 0.0) < currency_cooldown:
                return "currency_cooldown"
    return None


def entry_age_minutes(entry: dict[str, object], now: datetime) -> float | None:
    raw = entry.get("timestamp")
    if not raw:
        return None
    try:
        timestamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
    return max(0.0, (now - timestamp).total_seconds() / 60.0)


def instrument_currencies(instrument: str) -> tuple[str, str] | None:
    parts = str(instrument or "").split("_", 1)
    if len(parts) != 2:
        return None
    base, quote = parts
    if len(base) != 3 or len(quote) != 3:
        return None
    return base, quote


def load_state_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


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


def compact_error_text(value: object, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def describe_exception(exc: Exception) -> str:
    message = compact_error_text(exc)
    response = getattr(exc, "response", None)
    if response is None:
        return message
    status = getattr(response, "status_code", None)
    text = compact_error_text(getattr(response, "text", "") or "")
    if text:
        return f"{message} | response={status}: {text}"
    return message


def write_cycle_error(audit_path: Path, state_path: Path, *, cycle: int, error: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "timestamp": now,
        "cycle": cycle,
        "environment": "unknown",
        "dry_run": None,
        "blocked": ["cycle_error"],
        "health": {"ok": False, "reasons": ["cycle_error"], "details": {}},
        "action": {"action": "hold", "reason": "cycle_error"},
        "error": error,
    }
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")

    previous_state = {}
    if state_path.exists():
        try:
            previous_state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            previous_state = {}
    previous_state.update(
        {
            "timestamp": now,
            "cycle": cycle,
            "last_action": "cycle_error",
            "last_error": error,
            "consecutive_failures": int(previous_state.get("consecutive_failures", 0) or 0) + 1,
        }
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(previous_state, indent=2), encoding="utf-8")


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
        "scan_errors": payload.get("scan_errors") or [],
        "snapshot": {
            "nav": snapshot.nav,
            "balance": snapshot.balance,
            "open_trade_count": snapshot.open_trade_count,
            "positions_by_instrument": snapshot.positions_by_instrument,
        },
        "candidates": candidates[:10],
        "submission": submission or None,
        "decision_summary": payload.get("decision_summary"),
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
    recent_entries = prune_recent_entries(list(previous_state.get("recent_entries") or []))
    last_submission = previous_state.get("last_submission")
    for submission in payload.get("submissions") or []:
        if not isinstance(submission, dict):
            continue
        result = submission.get("result") or {}
        if result.get("submitted") or submission.get("error"):
            last_submission = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "instrument": submission.get("instrument"),
                "action": submission.get("action"),
                "score": submission.get("score"),
                "reason": submission.get("reason"),
                "submitted": bool(result.get("submitted")),
                "error": submission.get("error"),
            }
        if not result.get("submitted"):
            continue
        action = str(submission.get("action") or "")
        if action not in {"buy", "sell"}:
            continue
        recent_entries.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "instrument": submission.get("instrument"),
                "action": action,
                "score": submission.get("score"),
            }
        )
    recent_entries = prune_recent_entries(recent_entries)
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
        "recent_entries": recent_entries,
        "last_submission": last_submission,
        "open_trade_count": snapshot.open_trade_count,
        "positions_by_instrument": snapshot.positions_by_instrument,
        "active_positions": [
            {"instrument": name, "units": units, "side": "long" if units > 0 else "short"}
            for name, units in sorted(active_positions.items())
        ],
        "scan_errors": payload.get("scan_errors") or [],
        "latest_candidates": candidates[:10],
        "snapshot": {
            "nav": snapshot.nav,
            "balance": snapshot.balance,
            "open_trade_count": snapshot.open_trade_count,
            "positions_by_instrument": snapshot.positions_by_instrument,
        },
        "submission": payload.get("submission"),
        "decision_summary": payload.get("decision_summary"),
        "instrument_quality": update_instrument_quality(
            previous_state.get("instrument_quality") or {},
            payload.get("submissions") or [],
        ),
    }
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")


def update_instrument_quality(
    previous: dict[str, object],
    submissions: list[dict[str, object]],
    *,
    decay: float = 0.9985,
) -> dict[str, dict[str, float]]:
    quality: dict[str, dict[str, float]] = {}
    if isinstance(previous, dict):
        for instrument, stats in previous.items():
            if not isinstance(stats, dict):
                continue
            quality[str(instrument)] = {
                "fill_count": float(stats.get("fill_count", 0.0) or 0.0) * decay,
                "closed_count": float(stats.get("closed_count", 0.0) or 0.0) * decay,
                "net_pl": float(stats.get("net_pl", 0.0) or 0.0) * decay,
                "half_spread_cost": float(stats.get("half_spread_cost", 0.0) or 0.0) * decay,
            }

    for submission in submissions:
        if not isinstance(submission, dict):
            continue
        instrument = str(submission.get("instrument") or "")
        if not instrument:
            continue
        result = submission.get("result") or {}
        if not isinstance(result, dict) or not result.get("submitted"):
            continue
        response = result.get("response") or {}
        fill = response.get("orderFillTransaction") if isinstance(response, dict) else None
        if not isinstance(fill, dict):
            continue
        stats = quality.setdefault(
            instrument,
            {"fill_count": 0.0, "closed_count": 0.0, "net_pl": 0.0, "half_spread_cost": 0.0},
        )
        stats["fill_count"] += 1.0
        stats["half_spread_cost"] += _safe_number(fill.get("halfSpreadCost")) or 0.0
        pl = _safe_number(fill.get("pl")) or 0.0
        if pl or submission.get("action") == "close" or fill.get("tradesClosed") or fill.get("tradeReduced"):
            stats["closed_count"] += 1.0
            stats["net_pl"] += pl

    return {
        instrument: stats
        for instrument, stats in quality.items()
        if stats.get("fill_count", 0.0) >= 0.05 or abs(stats.get("net_pl", 0.0)) >= 0.001
    }


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


def prune_recent_entries(entries: list[dict[str, object]], *, max_age_hours: int = 24) -> list[dict[str, object]]:
    now = datetime.now(timezone.utc)
    pruned: list[dict[str, object]] = []
    for entry in entries:
        age = entry_age_minutes(entry, now)
        if age is None:
            continue
        if age <= max_age_hours * 60:
            pruned.append(entry)
    return pruned


if __name__ == "__main__":
    main()
