from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.backtest_open_window import replay_window


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sweep strategy settings against saved backtest candle files."
    )
    parser.add_argument(
        "--glob",
        default="data/backtest*.json",
        help="Glob for saved backtest files that include raw candles.",
    )
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--output", default="data/optimization_results.json")
    parser.add_argument("--target-win-rate", type=float, default=0.60)
    parser.add_argument("--min-trades", type=int, default=8)
    parser.add_argument("--long-thresholds", default="2.25,2.5,2.75,3.0")
    parser.add_argument("--short-thresholds", default="1.75,2.0,2.25,2.5")
    parser.add_argument("--regime-thresholds", default="1.0,1.25,1.5")
    parser.add_argument("--trailing-atr-multiples", default="0.75,1.0,1.25,1.5")
    parser.add_argument("--break-even-atr-multiples", default="0.5,1.0,1.5")
    parser.add_argument("--max-hold-candles", default="12,18,24,36")
    parser.add_argument("--spread-pips", type=float, default=0.00008)
    parser.add_argument("--slippage-pips", type=float, default=0.00002)
    parser.add_argument(
        "--allowed-hours-utc",
        default="21,22,23,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16",
    )
    parser.add_argument("--fast-window", type=int, default=5)
    parser.add_argument("--slow-window", type=int, default=20)
    parser.add_argument("--max-units", type=int, default=100)
    parser.add_argument("--max-open-trades", type=int, default=1)
    parser.add_argument("--risk-per-trade-fraction", type=float, default=0.0025)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    files = sorted(Path(".").glob(args.glob))
    datasets = load_datasets(files)
    if not datasets:
        raise SystemExit("No usable backtest files with candles were found.")

    candidates = list(iter_candidates(args))
    results = []
    for candidate in candidates:
        score_row = evaluate_candidate(candidate, datasets, args)
        results.append(score_row)

    results.sort(key=lambda item: item["objective_score"], reverse=True)
    top_results = results[: args.top]
    payload = {
        "input_files": [str(item["path"]) for item in datasets],
        "target_win_rate": args.target_win_rate,
        "candidate_count": len(results),
        "top_results": top_results,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"evaluated {len(results)} candidates across {len(datasets)} datasets")
    for idx, row in enumerate(top_results, start=1):
        print(
            f"{idx}. score={row['objective_score']:.4f} net={row['aggregate']['net_pnl']:.4f} "
            f"win_rate={row['aggregate']['win_rate']:.2%} trades={row['aggregate']['trade_count']} "
            f"drawdown={row['aggregate']['max_drawdown']:.4f}"
        )
        print(f"   flags: {format_candidate_flags(row['candidate'])}")
    print(f"wrote {output}")


def load_datasets(files: list[Path]) -> list[dict[str, object]]:
    datasets: list[dict[str, object]] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        candles = payload.get("candles")
        window_start = payload.get("window_start_utc")
        window_end = payload.get("window_end_utc")
        instrument = payload.get("instrument")
        granularity = payload.get("granularity")
        if not candles or not window_start or not window_end or not instrument or not granularity:
            continue
        datasets.append(
            {
                "path": path,
                "candles": candles,
                "window_start": window_start,
                "window_end": window_end,
                "instrument": instrument,
                "granularity": granularity,
            }
        )
    return datasets


def iter_candidates(args: argparse.Namespace):
    for long_threshold, short_threshold, regime_threshold, trailing_multiple, break_even_multiple, max_hold in itertools.product(
        parse_float_csv(args.long_thresholds),
        parse_float_csv(args.short_thresholds),
        parse_float_csv(args.regime_thresholds),
        parse_float_csv(args.trailing_atr_multiples),
        parse_float_csv(args.break_even_atr_multiples),
        parse_int_csv(args.max_hold_candles),
    ):
        yield {
            "long_score_threshold": long_threshold,
            "short_score_threshold": short_threshold,
            "regime_score_threshold": regime_threshold,
            "trailing_atr_multiple": trailing_multiple,
            "break_even_atr_multiple": break_even_multiple,
            "max_hold_candles": max_hold,
        }


def evaluate_candidate(
    candidate: dict[str, float | int],
    datasets: list[dict[str, object]],
    args: argparse.Namespace,
) -> dict[str, object]:
    rows = []
    setup_rollup: dict[str, dict[str, float]] = {}
    for dataset in datasets:
        replay_args = SimpleNamespace(
            instrument=dataset["instrument"],
            granularity=dataset["granularity"],
            window_start=dataset["window_start"],
            window_end=dataset["window_end"],
            window_hours=48,
            fetch_count=len(dataset["candles"]),
            fast_window=args.fast_window,
            slow_window=args.slow_window,
            units=args.max_units,
            max_units=args.max_units,
            max_open_trades=args.max_open_trades,
            risk_per_trade_fraction=args.risk_per_trade_fraction,
            long_score_threshold=candidate["long_score_threshold"],
            short_score_threshold=candidate["short_score_threshold"],
            regime_score_threshold=candidate["regime_score_threshold"],
            trailing_atr_multiple=candidate["trailing_atr_multiple"],
            break_even_atr_multiple=candidate["break_even_atr_multiple"],
            max_hold_candles=candidate["max_hold_candles"],
            spread_pips=args.spread_pips,
            slippage_pips=args.slippage_pips,
            allowed_hours_utc=args.allowed_hours_utc,
        )
        replay = replay_window(dataset["candles"], replay_args)
        rows.append(replay["summary"])
        merge_setup_summary(setup_rollup, replay.get("setup_summary", {}))

    aggregate = aggregate_summaries(rows)
    objective_score = score_summary(
        aggregate,
        target_win_rate=args.target_win_rate,
        min_trades=args.min_trades,
    )
    return {
        "candidate": candidate,
        "aggregate": aggregate,
        "objective_score": objective_score,
        "setup_summary": finalize_setup_summary(setup_rollup),
    }


def aggregate_summaries(rows: list[dict[str, object]]) -> dict[str, float]:
    if not rows:
        return {
            "trade_count": 0,
            "wins": 0,
            "losses": 0,
            "gross_pnl": 0.0,
            "net_pnl": 0.0,
            "win_rate": 0.0,
            "expectancy": 0.0,
            "max_drawdown": 0.0,
        }
    trade_count = int(sum(int(row.get("trade_count", 0) or 0) for row in rows))
    wins = int(sum(int(row.get("wins", 0) or 0) for row in rows))
    losses = int(sum(int(row.get("losses", 0) or 0) for row in rows))
    gross_pnl = float(sum(float(row.get("gross_pnl", 0.0) or 0.0) for row in rows))
    net_pnl = float(sum(float(row.get("net_pnl", 0.0) or 0.0) for row in rows))
    worst_drawdown = float(min(float(row.get("max_drawdown", 0.0) or 0.0) for row in rows))
    win_rate = (wins / trade_count) if trade_count else 0.0
    expectancy = (net_pnl / trade_count) if trade_count else 0.0
    return {
        "trade_count": trade_count,
        "wins": wins,
        "losses": losses,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "win_rate": win_rate,
        "expectancy": expectancy,
        "max_drawdown": worst_drawdown,
    }


def score_summary(summary: dict[str, float], *, target_win_rate: float, min_trades: int) -> float:
    net_pnl = float(summary.get("net_pnl", 0.0))
    win_rate = float(summary.get("win_rate", 0.0))
    trade_count = int(summary.get("trade_count", 0))
    max_drawdown = abs(float(summary.get("max_drawdown", 0.0)))
    expectancy = float(summary.get("expectancy", 0.0))

    win_rate_penalty = abs(target_win_rate - win_rate) * 0.25
    drawdown_penalty = max_drawdown * 0.75
    low_trade_penalty = 0.0 if trade_count >= min_trades else (min_trades - trade_count) * 0.02
    negative_pnl_penalty = abs(net_pnl) * 1.5 if net_pnl < 0 else 0.0
    expectancy_bonus = expectancy * 5.0

    return net_pnl + expectancy_bonus - win_rate_penalty - drawdown_penalty - low_trade_penalty - negative_pnl_penalty


def merge_setup_summary(
    aggregate: dict[str, dict[str, float]],
    incoming: dict[str, dict[str, float]],
) -> None:
    for key, metrics in incoming.items():
        row = aggregate.setdefault(
            key,
            {"trade_count": 0.0, "wins": 0.0, "losses": 0.0, "net_pnl": 0.0},
        )
        row["trade_count"] += float(metrics.get("trade_count", 0.0) or 0.0)
        row["wins"] += float(metrics.get("wins", 0.0) or 0.0)
        row["losses"] += float(metrics.get("losses", 0.0) or 0.0)
        row["net_pnl"] += float(metrics.get("net_pnl", 0.0) or 0.0)


def finalize_setup_summary(setup_rollup: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for key, metrics in setup_rollup.items():
        count = float(metrics.get("trade_count", 0.0) or 0.0)
        wins = float(metrics.get("wins", 0.0) or 0.0)
        result[key] = {
            "trade_count": count,
            "wins": wins,
            "losses": float(metrics.get("losses", 0.0) or 0.0),
            "net_pnl": float(metrics.get("net_pnl", 0.0) or 0.0),
            "win_rate": (wins / count) if count else 0.0,
            "expectancy": (float(metrics.get("net_pnl", 0.0) or 0.0) / count) if count else 0.0,
        }
    return result


def parse_float_csv(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def parse_int_csv(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def format_candidate_flags(candidate: dict[str, float | int]) -> str:
    return (
        f"--long-score-threshold {candidate['long_score_threshold']} "
        f"--short-score-threshold {candidate['short_score_threshold']} "
        f"--regime-score-threshold {candidate['regime_score_threshold']} "
        f"--trailing-atr-multiple {candidate['trailing_atr_multiple']} "
        f"--break-even-atr-multiple {candidate['break_even_atr_multiple']} "
        f"--max-hold-candles {candidate['max_hold_candles']}"
    )


if __name__ == "__main__":
    main()
