from __future__ import annotations

import argparse
import itertools
import json
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
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
from oanda_autotrader.execution import AccountSnapshot
from oanda_autotrader.indicators import atr
from oanda_autotrader.strategy import StrategyConfig, moving_average_crossover
from scripts.scan_forex_opportunities import (
    apply_entry_timing_confirmation_to_candidates,
    apply_instrument_scorecard_to_candidates,
    compact_external_signal,
    evaluate_entry_timing_confirmation,
    external_signal_adjustment,
    higher_timeframe_direction,
    instrument_class,
    instrument_class_counts,
    instrument_metadata,
    instrument_trade_units,
    opportunity_score,
    parse_signal_timestamp,
    required_submit_score,
    select_scan_instruments,
)


GRANULARITY_SECONDS = {"M5": 300, "M15": 900, "H1": 3600}
_ACTION_CACHE: dict[tuple[object, ...], object] = {}
_HTF_DIRECTION_CACHE: dict[tuple[object, ...], str] = {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cache recent candles and sweep current-style opportunity gates offline."
    )
    parser.add_argument("--accounts-path", default="accounts.yaml")
    parser.add_argument("--group", default="demo")
    parser.add_argument("--account", default="Primary")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--granularity", default="M5")
    parser.add_argument("--higher-timeframes", default="M15,H1")
    parser.add_argument("--count-buffer", type=int, default=120)
    parser.add_argument("--majors-only", action="store_true")
    parser.add_argument("--include-metals", action="store_true")
    parser.add_argument("--include-commodities", action="store_true")
    parser.add_argument("--max-instruments", type=int, default=0)
    parser.add_argument("--cache-path", default="data/research_last_week_candles.json")
    parser.add_argument("--output", default="data/research_opportunity_patterns.json")
    parser.add_argument("--use-cache", action="store_true")
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--top", type=int, default=12)
    parser.add_argument("--min-trades", type=int, default=12)
    parser.add_argument("--target-win-rate", type=float, default=0.60)
    parser.add_argument("--fast-window", type=int, default=5)
    parser.add_argument("--slow-window", type=int, default=20)
    parser.add_argument("--long-score-threshold", type=float, default=3.0)
    parser.add_argument("--short-score-threshold", type=float, default=1.75)
    parser.add_argument("--regime-score-threshold", type=float, default=1.25)
    parser.add_argument("--min-submit-scores", default="5.2,5.4,5.6")
    parser.add_argument("--non-liquid-min-submit-scores", default="5.5,5.75,6.0")
    parser.add_argument("--metal-submit-adds", default="0.35,0.45,0.55")
    parser.add_argument("--commodity-submit-adds", default="0.45,0.55,0.70")
    parser.add_argument("--max-spread-atr-ratios", default="0.65,0.80,1.00")
    parser.add_argument("--entry-extension-atrs", default="1.0,1.35,1.75")
    parser.add_argument("--htf-min-agreements", default="1,2")
    parser.add_argument("--higher-timeframe-agreement-bonus", type=float, default=0.35)
    parser.add_argument("--higher-timeframe-conflict-penalty", type=float, default=0.60)
    parser.add_argument("--higher-timeframe-max-score-bonus", type=float, default=0.75)
    parser.add_argument("--external-signals-path", default="")
    parser.add_argument("--external-signal-modes", default="rank,block,discount")
    parser.add_argument("--external-signal-max-age-minutes", type=float, default=240.0)
    parser.add_argument("--external-signal-max-adjustment", type=float, default=0.75)
    parser.add_argument("--external-signal-discount-threshold", type=float, default=0.55)
    parser.add_argument("--external-signal-threshold-discount", type=float, default=0.35)
    parser.add_argument("--require-external-signal-alignment", action="store_true")
    parser.add_argument("--disable-entry-timing-confirmation", action="store_true")
    parser.add_argument("--disable-higher-timeframe-confirmation", action="store_true")
    parser.add_argument("--max-hold-candles", type=int, default=36)
    parser.add_argument("--history-candles", type=int, default=180)
    parser.add_argument("--spread-r-multiple", type=float, default=0.08)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.use_cache and Path(args.cache_path).exists():
        dataset = json.loads(Path(args.cache_path).read_text(encoding="utf-8"))
    else:
        dataset = fetch_research_candles(args)
        cache_path = Path(args.cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
        print(f"cached candles to {cache_path}")
    dataset = limit_cached_dataset(dataset, args.max_instruments)

    if args.download_only:
        print_cache_summary(dataset)
        return

    external_signals = load_research_external_signals(args.external_signals_path)
    configs = list(iter_research_configs(args))
    results = [evaluate_research_config(dataset, config, args, external_signals) for config in configs]
    results.sort(key=lambda row: row["objective_score"], reverse=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cache_path": args.cache_path,
        "dataset_summary": dataset_summary(dataset),
        "external_signal_summary": research_external_signal_summary(external_signals),
        "candidate_count": len(results),
        "target_win_rate": args.target_win_rate,
        "top_results": results[: args.top],
        "all_results": results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"evaluated {len(results)} settings across {len(dataset.get('instruments', {}))} instruments")
    for index, row in enumerate(payload["top_results"], start=1):
        summary = row["summary"]
        print(
            f"{index}. score={row['objective_score']:.3f} trades={summary['trade_count']} "
            f"win={summary['win_rate']:.1%} pf={summary['profit_factor']:.2f} "
            f"net_r={summary['net_r']:.2f} dd={summary['max_drawdown_r']:.2f}"
        )
        print(f"   {format_config(row['config'])}")
    print(f"wrote {output}")


def fetch_research_candles(args: argparse.Namespace) -> dict[str, object]:
    groups = load_account_groups_or_default(args.accounts_path)
    group, entry = select_account(groups, args.group, args.account)
    app_config = resolve_account_credentials(group, entry)
    account_client = build_account_client(app_config)
    instruments_client = build_instruments_client(app_config)
    tradeable = account_client.get_instruments(app_config.account_id).get("instruments", [])
    metadata = instrument_metadata(tradeable)
    instruments = select_scan_instruments(
        tradeable,
        majors_only=args.majors_only,
        include_metals=args.include_metals,
        include_commodities=args.include_commodities,
    )
    if args.max_instruments > 0:
        instruments = instruments[: args.max_instruments]
    granularities = [args.granularity] + parse_csv(args.higher_timeframes)
    counts = {
        granularity: candle_count_for_days(args.days, granularity, args.count_buffer)
        for granularity in granularities
    }
    data: dict[str, object] = {
        "account_id": app_config.account_id,
        "environment": app_config.environment,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": args.days,
        "granularities": granularities,
        "instrument_classes": instrument_class_counts(instruments, metadata),
        "instruments": {},
    }
    for index, instrument in enumerate(instruments, start=1):
        rows: dict[str, object] = {}
        for granularity in granularities:
            payload = instruments_client.get_candles(
                instrument,
                price="M",
                granularity=granularity,
                count=counts[granularity],
            )
            rows[granularity] = payload.get("candles", [])
        data["instruments"][instrument] = {
            "metadata": metadata.get(instrument, {}),
            "candles": rows,
        }
        print(f"fetched {index}/{len(instruments)} {instrument}")
    return data


def candle_count_for_days(days: int, granularity: str, buffer: int) -> int:
    seconds = GRANULARITY_SECONDS.get(granularity.upper(), 300)
    return min(5000, int(days * 86400 / seconds) + max(0, buffer))


def evaluate_research_config(
    dataset: dict[str, object],
    config: dict[str, object],
    args: argparse.Namespace,
    external_signals: dict[str, list[dict[str, object]]] | None = None,
) -> dict[str, object]:
    all_trades: list[dict[str, object]] = []
    gate_counts: dict[str, int] = {}
    by_instrument: dict[str, dict[str, object]] = {}
    for instrument, row in (dataset.get("instruments") or {}).items():
        result = replay_instrument(str(instrument), row, config, args, external_signals or {})
        all_trades.extend(result["trades"])
        merge_counts(gate_counts, result["gate_counts"])
        if result["summary"]["trade_count"]:
            by_instrument[str(instrument)] = result["summary"]
    summary = summarize_r_trades(all_trades)
    objective = score_research_summary(summary, gate_counts, args)
    return {
        "config": config,
        "summary": summary,
        "objective_score": objective,
        "gate_counts": dict(sorted(gate_counts.items(), key=lambda item: item[1], reverse=True)),
        "best_instruments": sorted(
            [{"instrument": key, **value} for key, value in by_instrument.items()],
            key=lambda item: float(item.get("net_r", 0.0)),
            reverse=True,
        )[:10],
        "worst_instruments": sorted(
            [{"instrument": key, **value} for key, value in by_instrument.items()],
            key=lambda item: float(item.get("net_r", 0.0)),
        )[:10],
    }


def replay_instrument(
    instrument: str,
    row: object,
    config: dict[str, object],
    args: argparse.Namespace,
    external_signals: dict[str, list[dict[str, object]]] | None = None,
) -> dict[str, object]:
    payload = row if isinstance(row, dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    candles_by_granularity = payload.get("candles") if isinstance(payload.get("candles"), dict) else {}
    candles = list(candles_by_granularity.get(args.granularity) or [])
    htf = {
        granularity: list(candles_by_granularity.get(granularity) or [])
        for granularity in parse_csv(args.higher_timeframes)
    }
    htf_times = {
        granularity: [parse_ts(candle["time"]) for candle in rows if candle.get("time")]
        for granularity, rows in htf.items()
    }
    strategy = StrategyConfig(
        instrument=instrument,
        fast_window=args.fast_window,
        slow_window=args.slow_window,
        units=instrument_trade_units(instrument, metadata, SimpleNamespace(max_units=100, metal_units=0.1, commodity_units=1.0)),
        long_score_threshold=args.long_score_threshold,
        short_score_threshold=args.short_score_threshold,
        regime_score_threshold=args.regime_score_threshold,
    )
    sim_args = SimpleNamespace(
        min_submit_score=config["min_submit_score"],
        non_liquid_min_submit_score=config["non_liquid_min_submit_score"],
        metal_submit_score_add=config["metal_submit_score_add"],
        commodity_submit_score_add=config["commodity_submit_score_add"],
        allow_non_liquid_trades=True,
        disable_entry_timing_confirmation=bool(config["disable_entry_timing_confirmation"]),
        entry_timing_max_extension_atr=config["entry_timing_max_extension_atr"],
        entry_timing_buy_max_rsi=72.0,
        entry_timing_sell_min_rsi=28.0,
    )
    trades: list[dict[str, object]] = []
    gate_counts: dict[str, int] = {}
    open_trade: dict[str, object] | None = None
    snapshot_position = 0.0
    for index, candle in enumerate(candles):
        history_start = max(0, index - max(int(args.history_candles), args.slow_window + 20) + 1)
        history = candles[history_start : index + 1]
        close = mid_value(candle, "c")
        high = mid_value(candle, "h")
        low = mid_value(candle, "l")
        if close is None or high is None or low is None:
            continue
        if open_trade is not None:
            closed = maybe_close_research_trade(open_trade, candle, index, config, args)
            if closed is not None:
                trades.append(closed)
                open_trade = None
                snapshot_position = 0.0
            else:
                continue
        if open_trade is not None or len(history) < args.slow_window + 2:
            continue
        action = cached_research_action(
            instrument=instrument,
            granularity=args.granularity,
            index=index,
            history=history,
            strategy=strategy,
        )
        latest_atr = float((action.metadata or {}).get("atr") or 0.0)
        if latest_atr <= 0:
            latest_atr = safe_atr(history, strategy.atr_period) or 0.0
        if latest_atr is None or latest_atr <= 0:
            continue
        score = opportunity_score(action.action, action.metadata or {}, latest_atr)
        candidate = {
            "instrument": instrument,
            "action": action.action,
            "score": score,
            "metadata": dict(action.metadata or {}),
            "atr": latest_atr,
            "entry_timing_confirmation": evaluate_entry_timing_confirmation(
                action.action,
                history,
                dict(action.metadata or {}),
                latest_atr,
                sim_args,
            ),
        }
        candidate["required_score"] = required_submit_score(instrument, sim_args, {})
        if action.action not in {"buy", "sell"}:
            increment(gate_counts, "hold")
            continue
        external_signal_mode = str(config.get("external_signal_mode") or "rank").lower()
        if external_signal_mode != "discount" and float(candidate.get("score", 0.0) or 0.0) < float(candidate.get("required_score", 0.0) or 0.0):
            candidate["blocked_reason"] = "below_submit_threshold"
            increment(gate_counts, str(candidate["blocked_reason"]))
            continue
        signal_adjustment = apply_research_external_signals(
            candidate,
            external_signals or {},
            candle_time=parse_ts(candle["time"]),
            args=args,
            mode=external_signal_mode,
        )
        if signal_adjustment is None and bool(getattr(args, "require_external_signal_alignment", False)):
            increment(gate_counts, "external_signal_missing")
            continue
        if external_signal_mode == "discount" and float(candidate.get("score", 0.0) or 0.0) < float(candidate.get("required_score", 0.0) or 0.0):
            candidate["blocked_reason"] = "below_submit_threshold"
        apply_entry_timing_confirmation_to_candidates([candidate], sim_args)
        if candidate.get("blocked_reason"):
            increment(gate_counts, str(candidate["blocked_reason"]))
            continue
        htf_confirmation = higher_timeframe_research_confirmation(
            instrument=instrument,
            action=str(action.action),
            candle_time=parse_ts(candle["time"]),
            htf=htf,
            htf_times=htf_times,
            strategy=strategy,
            min_agreements=int(config["htf_min_agreements"]),
            disabled=bool(config["disable_higher_timeframe_confirmation"]),
        )
        htf_adjustment = higher_timeframe_research_score_adjustment(htf_confirmation, config)
        if htf_confirmation:
            candidate["higher_timeframe_confirmation"] = htf_confirmation
            candidate["higher_timeframe_score_adjustment"] = htf_adjustment
            candidate["pre_higher_timeframe_score"] = candidate["score"]
            candidate["score"] = max(0.0, float(candidate["score"]) + htf_adjustment)
            candidate["metadata"]["higher_timeframe_confirmation"] = htf_confirmation
            candidate["metadata"]["higher_timeframe_score_adjustment"] = htf_adjustment
        if htf_confirmation and not htf_confirmation.get("confirmed"):
            increment(gate_counts, "higher_timeframe_not_confirmed")
            continue
        spread_ratio = simulated_spread_atr_ratio(instrument)
        if spread_ratio > float(config["max_spread_atr_ratio"]):
            increment(gate_counts, "simulated_spread_too_wide")
            continue
        stop = abs(close - float(action.stop_loss_price or close)) or latest_atr
        target = abs(float(action.take_profit_price or close) - close) or stop * 2.0
        open_trade = {
            "instrument": instrument,
            "side": "long" if action.action == "buy" else "short",
            "entry_time": candle["time"],
            "entry_index": index,
            "entry_price": close,
            "stop_price": close - stop if action.action == "buy" else close + stop,
            "target_price": close + target if action.action == "buy" else close - target,
            "stop_distance": stop,
            "target_distance": target,
            "score": candidate["score"],
            "setup_reason": action.reason,
            "spread_r": float(args.spread_r_multiple) + spread_ratio * 0.02,
        }
        snapshot_position = float(action.units if action.action == "buy" else -action.units)
        increment(gate_counts, "opened")
    if open_trade is not None and candles:
        final_close = mid_value(candles[-1], "c")
        if final_close is not None:
            trades.append(close_research_trade(open_trade, candles[-1]["time"], final_close, "forced_end"))
    return {"trades": trades, "gate_counts": gate_counts, "summary": summarize_r_trades(trades)}


def apply_research_external_signals(
    candidate: dict[str, object],
    signals_by_instrument: dict[str, list[dict[str, object]]],
    *,
    candle_time: datetime,
    args: argparse.Namespace,
    mode: str = "rank",
) -> float | None:
    instrument = str(candidate.get("instrument") or "").upper()
    action = str(candidate.get("action") or "").lower()
    if action not in {"buy", "sell"}:
        return None
    signals = active_research_external_signals(
        signals_by_instrument.get(instrument) or [],
        candle_time=candle_time,
        max_age_minutes=float(getattr(args, "external_signal_max_age_minutes", 240.0) or 0.0),
    )
    if not signals:
        return None
    mode_name = str(mode or "rank").lower()
    max_adjustment = max(0.0, float(getattr(args, "external_signal_max_adjustment", 0.75) or 0.0))
    if max_adjustment <= 0:
        return None
    adjustment = 0.0
    applied: list[dict[str, object]] = []
    for signal in signals:
        signal_adjustment = external_signal_adjustment(signal, action, max_adjustment)
        if signal_adjustment == 0:
            continue
        adjustment += signal_adjustment
        applied.append(compact_external_signal(signal, signal_adjustment))
    adjustment = max(-max_adjustment, min(max_adjustment, adjustment))
    if not applied or adjustment == 0:
        return None
    candidate["pre_external_signal_score"] = candidate.get("score")
    candidate["external_signal_score_adjustment"] = adjustment
    candidate["external_signals"] = applied
    if mode_name in {"rank", "block", "discount"}:
        candidate["score"] = max(0.0, float(candidate.get("score", 0.0) or 0.0) + adjustment)
    if mode_name == "discount" and adjustment >= float(getattr(args, "external_signal_discount_threshold", 0.55) or 0.55):
        discount = abs(float(getattr(args, "external_signal_threshold_discount", 0.35) or 0.0))
        candidate["pre_external_signal_required_score"] = candidate.get("required_score")
        candidate["required_score"] = max(0.0, float(candidate.get("required_score", 0.0) or 0.0) - discount)
        candidate["external_signal_threshold_discount"] = discount
    metadata = dict(candidate.get("metadata") or {})
    metadata["external_signal_score_adjustment"] = adjustment
    metadata["external_signals"] = applied
    if candidate.get("external_signal_threshold_discount") is not None:
        metadata["external_signal_threshold_discount"] = candidate["external_signal_threshold_discount"]
    candidate["metadata"] = metadata
    if mode_name == "block" and float(candidate["score"]) < float(candidate.get("required_score", 0.0) or 0.0):
        candidate["blocked_reason"] = "external_signal_conflict"
    return adjustment


def active_research_external_signals(
    signals: list[dict[str, object]],
    *,
    candle_time: datetime,
    max_age_minutes: float,
) -> list[dict[str, object]]:
    active = []
    for signal in signals:
        timestamp = signal.get("_timestamp")
        if not isinstance(timestamp, datetime):
            continue
        age_minutes = (candle_time - timestamp).total_seconds() / 60.0
        if age_minutes < 0:
            continue
        if max_age_minutes > 0 and age_minutes > max_age_minutes:
            continue
        active.append(signal)
    return active


def load_research_external_signals(path_value: str) -> dict[str, list[dict[str, object]]]:
    if not path_value:
        return {}
    path = Path(path_value)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    raw_signals = payload.get("signals") if isinstance(payload, dict) else payload
    if not isinstance(raw_signals, list):
        return {}
    generated_at = payload.get("generated_at") if isinstance(payload, dict) else None
    by_instrument: dict[str, list[dict[str, object]]] = {}
    for raw in raw_signals:
        if not isinstance(raw, dict):
            continue
        timestamp = parse_signal_timestamp(raw.get("timestamp") or raw.get("generated_at") or generated_at)
        if timestamp is None:
            continue
        instruments = raw.get("instruments")
        if isinstance(instruments, str):
            names = [instruments]
        elif isinstance(instruments, list):
            names = [str(item) for item in instruments]
        else:
            names = [str(raw.get("instrument") or "")]
        for name in names:
            instrument = str(name or "").strip().upper()
            if not instrument:
                continue
            signal = dict(raw)
            signal["instrument"] = instrument
            signal["_timestamp"] = timestamp
            signal["timestamp"] = timestamp.isoformat()
            by_instrument.setdefault(instrument, []).append(signal)
    for rows in by_instrument.values():
        rows.sort(key=lambda item: item["_timestamp"])
    return by_instrument


def research_external_signal_summary(signals_by_instrument: dict[str, list[dict[str, object]]]) -> dict[str, object]:
    return {
        "instrument_count": len(signals_by_instrument),
        "signal_count": sum(len(items) for items in signals_by_instrument.values()),
        "instruments": sorted(signals_by_instrument)[:25],
    }


def cached_research_action(
    *,
    instrument: str,
    granularity: str,
    index: int,
    history: list[dict],
    strategy: StrategyConfig,
):
    key = (
        instrument,
        granularity,
        index,
        strategy.fast_window,
        strategy.slow_window,
        strategy.long_score_threshold,
        strategy.short_score_threshold,
        strategy.regime_score_threshold,
        strategy.atr_stop_multiple,
        strategy.atr_target_multiple,
        strategy.min_risk_reward_ratio,
    )
    cached = _ACTION_CACHE.get(key)
    if cached is not None:
        return cached
    snapshot = AccountSnapshot(
        environment="practice",
        account_id="research",
        nav=100000.0,
        balance=100000.0,
        open_trade_count=0,
        positions_by_instrument={instrument: 0.0},
    )
    action = moving_average_crossover(history, strategy, snapshot)
    _ACTION_CACHE[key] = action
    return action


def maybe_close_research_trade(
    trade: dict[str, object],
    candle: dict[str, object],
    index: int,
    config: dict[str, object],
    args: argparse.Namespace,
) -> dict[str, object] | None:
    high = mid_value(candle, "h")
    low = mid_value(candle, "l")
    close = mid_value(candle, "c")
    if high is None or low is None or close is None:
        return None
    side = str(trade["side"])
    if side == "long":
        if low <= float(trade["stop_price"]):
            return close_research_trade(trade, str(candle["time"]), float(trade["stop_price"]), "stop_loss")
        if high >= float(trade["target_price"]):
            return close_research_trade(trade, str(candle["time"]), float(trade["target_price"]), "take_profit")
    else:
        if high >= float(trade["stop_price"]):
            return close_research_trade(trade, str(candle["time"]), float(trade["stop_price"]), "stop_loss")
        if low <= float(trade["target_price"]):
            return close_research_trade(trade, str(candle["time"]), float(trade["target_price"]), "take_profit")
    if index - int(trade["entry_index"]) >= int(args.max_hold_candles):
        return close_research_trade(trade, str(candle["time"]), close, "max_hold")
    return None


def close_research_trade(
    trade: dict[str, object],
    exit_time: str,
    exit_price: float,
    reason: str,
) -> dict[str, object]:
    side = str(trade["side"])
    entry = float(trade["entry_price"])
    stop_distance = max(float(trade["stop_distance"]), 1e-9)
    if side == "long":
        gross_r = (exit_price - entry) / stop_distance
    else:
        gross_r = (entry - exit_price) / stop_distance
    net_r = gross_r - float(trade.get("spread_r", 0.0) or 0.0)
    return {
        **trade,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": reason,
        "gross_r": gross_r,
        "net_r": net_r,
    }


def higher_timeframe_research_confirmation(
    *,
    instrument: str,
    action: str,
    candle_time: datetime,
    htf: dict[str, list[dict]],
    htf_times: dict[str, list[datetime]],
    strategy: StrategyConfig,
    min_agreements: int,
    disabled: bool,
) -> dict[str, object] | None:
    if disabled or action not in {"buy", "sell"}:
        return None
    agreements = 0
    conflicts = 0
    missing = 0
    details: list[dict[str, object]] = []
    for granularity, htf_rows in htf.items():
        times = htf_times.get(granularity) or []
        idx = bisect_right(times, candle_time) - 1
        if idx < max(strategy.slow_window, 1):
            missing += 1
            details.append({"granularity": granularity, "direction": "missing", "reason": "insufficient_history"})
            continue
        key = (
            instrument,
            granularity,
            idx,
            strategy.fast_window,
            strategy.slow_window,
            strategy.long_score_threshold,
            strategy.short_score_threshold,
            strategy.regime_score_threshold,
        )
        direction = _HTF_DIRECTION_CACHE.get(key)
        if direction is None:
            history_start = max(0, idx - 180 + 1)
            history = htf_rows[history_start : idx + 1]
            direction = higher_timeframe_direction(
                cached_research_action(
                    instrument=instrument,
                    granularity=granularity,
                    index=idx,
                    history=history,
                    strategy=strategy,
                )
            )
            _HTF_DIRECTION_CACHE[key] = direction
        if direction == action:
            agreements += 1
        elif direction in {"buy", "sell"}:
            conflicts += 1
        details.append({"granularity": granularity, "direction": direction})
    confirmed = agreements >= min_agreements and conflicts == 0
    reason = "confirmed"
    if agreements < min_agreements:
        reason = "insufficient_higher_timeframe_agreement"
    elif conflicts:
        reason = "higher_timeframe_conflict"
    return {
        "confirmed": confirmed,
        "reason": reason,
        "desired_action": action,
        "agreements": agreements,
        "conflicts": conflicts,
        "missing": missing,
        "min_agreements": min_agreements,
        "granularities": details,
    }


def higher_timeframe_research_score_adjustment(
    confirmation: dict[str, object] | None,
    config: dict[str, object],
) -> float:
    if not confirmation:
        return 0.0
    agreements = max(0, int(confirmation.get("agreements", 0) or 0))
    conflicts = max(0, int(confirmation.get("conflicts", 0) or 0))
    bonus = agreements * float(config.get("higher_timeframe_agreement_bonus", 0.35) or 0.0)
    max_bonus = max(0.0, float(config.get("higher_timeframe_max_score_bonus", 0.75) or 0.0))
    penalty = conflicts * float(config.get("higher_timeframe_conflict_penalty", 0.60) or 0.0)
    return min(max_bonus, bonus) - penalty


def summarize_r_trades(trades: list[dict[str, object]]) -> dict[str, object]:
    if not trades:
        return {
            "trade_count": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "gross_r": 0.0,
            "net_r": 0.0,
            "expectancy_r": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_r": 0.0,
        }
    wins = [float(t["net_r"]) for t in trades if float(t["net_r"]) > 0]
    losses = [float(t["net_r"]) for t in trades if float(t["net_r"]) < 0]
    net_r = sum(float(t["net_r"]) for t in trades)
    gross_r = sum(float(t["gross_r"]) for t in trades)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for trade in trades:
        equity += float(trade["net_r"])
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    return {
        "trade_count": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(trades),
        "gross_r": gross_r,
        "net_r": net_r,
        "expectancy_r": net_r / len(trades),
        "profit_factor": gross_win / gross_loss if gross_loss else (999.0 if gross_win else 0.0),
        "max_drawdown_r": max_drawdown,
    }


def score_research_summary(summary: dict[str, object], gate_counts: dict[str, int], args: argparse.Namespace) -> float:
    trade_count = int(summary.get("trade_count", 0) or 0)
    net_r = float(summary.get("net_r", 0.0) or 0.0)
    win_rate = float(summary.get("win_rate", 0.0) or 0.0)
    profit_factor = float(summary.get("profit_factor", 0.0) or 0.0)
    drawdown = abs(float(summary.get("max_drawdown_r", 0.0) or 0.0))
    low_trade_penalty = max(0, int(args.min_trades) - trade_count) * 0.35
    win_gap_penalty = max(0.0, float(args.target_win_rate) - win_rate) * 5.0
    pf_bonus = min(3.0, profit_factor) * 0.6
    return net_r + pf_bonus - drawdown * 0.45 - low_trade_penalty - win_gap_penalty


def iter_research_configs(args: argparse.Namespace):
    for values in itertools.product(
        parse_float_csv(args.min_submit_scores),
        parse_float_csv(args.non_liquid_min_submit_scores),
        parse_float_csv(args.metal_submit_adds),
        parse_float_csv(args.commodity_submit_adds),
        parse_float_csv(args.max_spread_atr_ratios),
        parse_float_csv(args.entry_extension_atrs),
        parse_int_csv(args.htf_min_agreements),
        parse_csv(args.external_signal_modes),
        [True] if args.disable_entry_timing_confirmation else [False, True],
        [True] if args.disable_higher_timeframe_confirmation else [False, True],
    ):
        (
            min_submit,
            non_liquid,
            metal_add,
            commodity_add,
            spread_ratio,
            extension_atr,
            htf_min,
            external_signal_mode,
            disable_timing,
            disable_htf,
        ) = values
        yield {
            "min_submit_score": min_submit,
            "non_liquid_min_submit_score": non_liquid,
            "metal_submit_score_add": metal_add,
            "commodity_submit_score_add": commodity_add,
            "max_spread_atr_ratio": spread_ratio,
            "entry_timing_max_extension_atr": extension_atr,
            "htf_min_agreements": htf_min,
            "higher_timeframe_agreement_bonus": float(args.higher_timeframe_agreement_bonus),
            "higher_timeframe_conflict_penalty": float(args.higher_timeframe_conflict_penalty),
            "higher_timeframe_max_score_bonus": float(args.higher_timeframe_max_score_bonus),
            "external_signal_mode": str(external_signal_mode).lower(),
            "disable_entry_timing_confirmation": disable_timing,
            "disable_higher_timeframe_confirmation": disable_htf,
        }


def simulated_spread_atr_ratio(instrument: str) -> float:
    cls = instrument_class(instrument)
    if cls == "metal":
        return 0.70
    if cls == "commodity":
        return 0.85
    if instrument in {
        "EUR_USD",
        "USD_JPY",
        "GBP_USD",
        "USD_CAD",
        "AUD_USD",
        "USD_CHF",
        "NZD_USD",
        "EUR_GBP",
        "EUR_JPY",
        "GBP_JPY",
    }:
        return 0.25
    return 0.55


def dataset_summary(dataset: dict[str, object]) -> dict[str, object]:
    instruments = dataset.get("instruments") or {}
    counts = {}
    for _instrument, row in instruments.items():
        candles = row.get("candles", {}) if isinstance(row, dict) else {}
        for granularity, values in candles.items():
            counts[granularity] = counts.get(granularity, 0) + len(values or [])
    return {
        "instrument_count": len(instruments),
        "instrument_classes": dataset.get("instrument_classes"),
        "candle_counts": counts,
        "days": dataset.get("days"),
    }


def limit_cached_dataset(dataset: dict[str, object], max_instruments: int) -> dict[str, object]:
    if max_instruments <= 0:
        return dataset
    instruments = dataset.get("instruments")
    if not isinstance(instruments, dict) or len(instruments) <= max_instruments:
        return dataset
    limited = dict(dataset)
    limited["instruments"] = dict(list(instruments.items())[:max_instruments])
    return limited


def print_cache_summary(dataset: dict[str, object]) -> None:
    print(json.dumps(dataset_summary(dataset), indent=2))


def format_config(config: dict[str, object]) -> str:
    return " ".join(f"{key}={value}" for key, value in config.items())


def merge_counts(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + int(value)


def increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def parse_csv(value: str) -> list[str]:
    return [item.strip().upper() for item in str(value or "").split(",") if item.strip()]


def parse_float_csv(value: str) -> list[float]:
    return [float(item.strip()) for item in str(value or "").split(",") if item.strip()]


def parse_int_csv(value: str) -> list[int]:
    return [int(item.strip()) for item in str(value or "").split(",") if item.strip()]


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def safe_atr(candles: list[dict], period: int) -> float | None:
    try:
        return atr(candles, period)
    except ValueError:
        return None


def mid_value(candle: dict[str, object], key: str) -> float | None:
    try:
        return float((candle.get("mid") or {}).get(key))
    except (TypeError, ValueError, AttributeError):
        return None


if __name__ == "__main__":
    main()
