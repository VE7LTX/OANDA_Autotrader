from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from oanda_autotrader.ai import (
    HeuristicDecisionProvider,
    JsonFileDecisionProvider,
    MarketContext,
)
from oanda_autotrader.app import build_account_client, build_instruments_client
from oanda_autotrader.config import (
    load_account_groups_or_default,
    resolve_account_credentials,
    select_account,
)
from oanda_autotrader.execution import (
    PracticeExecutionEngine,
    RiskPolicy,
    snapshot_from_account_payload,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a constrained AI trading experiment against an OANDA practice account."
    )
    parser.add_argument("--accounts-path", default="accounts.yaml")
    parser.add_argument("--group", default="demo")
    parser.add_argument("--account", default="Primary")
    parser.add_argument("--instrument", default="USD_CAD")
    parser.add_argument("--granularity", default="M5")
    parser.add_argument("--count", type=int, default=120)
    parser.add_argument(
        "--decision-source",
        choices=("heuristic", "json-file"),
        default="heuristic",
    )
    parser.add_argument("--decision-file")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--max-units", type=int, default=100)
    parser.add_argument("--max-open-trades", type=int, default=1)
    parser.add_argument("--min-confidence", type=float, default=0.55)
    parser.add_argument("--allow-instrument", action="append", default=[])
    parser.add_argument("--audit-path", default="data/ai_trade_audit.jsonl")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    groups = load_account_groups_or_default(args.accounts_path)
    group, entry = select_account(groups, args.group, args.account)
    resolved = resolve_account_credentials(group, entry)

    account_client = build_account_client(resolved)
    instruments_client = build_instruments_client(resolved)
    summary = account_client.get_account_summary(resolved.account_id)
    details = account_client.get_account(resolved.account_id)
    candles_payload = instruments_client.get_candles(
        args.instrument,
        price="M",
        granularity=args.granularity,
        count=args.count,
    )
    candles = candles_payload.get("candles", [])

    context = MarketContext(
        account=details,
        summary=summary,
        candles=candles,
        instrument=args.instrument,
        granularity=args.granularity,
        metadata={
            "group": group.key,
            "account_name": entry.name,
            "environment": resolved.environment,
        },
    )

    provider = build_provider(args)
    action = provider.decide(context)
    snapshot = snapshot_from_account_payload(resolved, details, summary)
    policy = RiskPolicy(
        practice_only=True,
        allowed_instruments=tuple(args.allow_instrument or [args.instrument]),
        max_units_per_trade=args.max_units,
        max_open_trades=args.max_open_trades,
        min_confidence=args.min_confidence,
    )
    engine = PracticeExecutionEngine(resolved, policy)
    result = engine.execute(
        action,
        snapshot,
        dry_run=(not args.submit) or args.dry_run,
    )
    emit_audit_record(args.audit_path, context, action, result)
    print(
        json.dumps(
            {
                "context": context.to_prompt_payload(),
                "action": action.__dict__,
                "result": result,
            },
            indent=2,
        )
    )


def build_provider(args: argparse.Namespace):
    if args.decision_source == "json-file":
        if not args.decision_file:
            raise ValueError("--decision-file is required for --decision-source json-file")
        return JsonFileDecisionProvider(args.decision_file)
    return HeuristicDecisionProvider(units=args.max_units)


def emit_audit_record(
    path: str, context: MarketContext, action, result: dict[str, object]
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "context": context.to_prompt_payload(),
        "action": action.__dict__,
        "result": result,
    }
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    main()
