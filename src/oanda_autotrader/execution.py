"""
Practice-only execution policy and order submission helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .app import build_orders_client
from .config import AppConfig


@dataclass(frozen=True)
class TradeAction:
    action: str
    instrument: str
    units: int = 0
    confidence: float = 0.0
    reason: str = ""
    stop_loss_price: str | None = None
    take_profit_price: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AccountSnapshot:
    environment: str
    account_id: str
    nav: float | None
    balance: float | None
    open_trade_count: int
    positions_by_instrument: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RiskPolicy:
    practice_only: bool = True
    allowed_instruments: tuple[str, ...] = ()
    max_units_per_trade: int = 1000
    max_open_trades: int = 3
    min_confidence: float = 0.55
    require_stop_loss: bool = True
    time_in_force: str = "FOK"
    position_fill: str = "DEFAULT"

    def allows_instrument(self, instrument: str) -> bool:
        return not self.allowed_instruments or instrument in self.allowed_instruments


class PracticeExecutionEngine:
    def __init__(self, config: AppConfig, policy: RiskPolicy) -> None:
        self.config = config
        self.policy = policy
        self.orders = build_orders_client(config)

    def validate_action(self, action: TradeAction, snapshot: AccountSnapshot) -> None:
        kind = action.action.lower()
        if self.policy.practice_only and self.config.environment != "practice":
            raise ValueError("PracticeExecutionEngine refuses to trade on non-practice accounts.")
        if kind not in {"hold", "buy", "sell", "close"}:
            raise ValueError(f"Unsupported action '{action.action}'.")
        if not self.policy.allows_instrument(action.instrument):
            raise ValueError(f"Instrument '{action.instrument}' is not in the allowed list.")
        if kind == "hold":
            return
        if snapshot.open_trade_count >= self.policy.max_open_trades and kind != "close":
            raise ValueError("Open trade limit reached.")
        if action.confidence < self.policy.min_confidence:
            raise ValueError(
                f"Confidence {action.confidence:.3f} is below the policy threshold."
            )
        if kind in {"buy", "sell"} and action.units <= 0:
            raise ValueError("Trade units must be positive.")
        if kind in {"buy", "sell"} and action.units > self.policy.max_units_per_trade:
            raise ValueError("Trade units exceed the policy max.")
        if self.policy.require_stop_loss and kind in {"buy", "sell"} and not action.stop_loss_price:
            raise ValueError("Stop loss is required by policy.")

    def execute(
        self, action: TradeAction, snapshot: AccountSnapshot, *, dry_run: bool = True
    ) -> dict[str, Any]:
        self.validate_action(action, snapshot)
        kind = action.action.lower()
        if kind == "hold":
            return {
                "submitted": False,
                "dry_run": dry_run,
                "reason": "hold",
                "order": None,
            }

        order = self._build_order(action, snapshot)
        if dry_run:
            return {
                "submitted": False,
                "dry_run": True,
                "reason": "dry_run",
                "order": order,
            }

        response = self.orders.create_order(self.config.account_id, order)
        return {
            "submitted": True,
            "dry_run": False,
            "order": order,
            "response": response,
        }

    def _build_order(
        self, action: TradeAction, snapshot: AccountSnapshot
    ) -> dict[str, Any]:
        kind = action.action.lower()
        if kind in {"buy", "sell"}:
            signed_units = action.units if kind == "buy" else -action.units
        else:
            net_units = snapshot.positions_by_instrument.get(action.instrument, 0)
            if net_units == 0:
                raise ValueError(
                    f"Cannot close '{action.instrument}' because no open position was found."
                )
            signed_units = -net_units

        order: dict[str, Any] = {
            "type": "MARKET",
            "instrument": action.instrument,
            "units": str(signed_units),
            "timeInForce": self.policy.time_in_force,
            "positionFill": self.policy.position_fill,
        }
        if action.stop_loss_price:
            order["stopLossOnFill"] = {"price": str(action.stop_loss_price)}
        if action.take_profit_price:
            order["takeProfitOnFill"] = {"price": str(action.take_profit_price)}
        return order


def snapshot_from_account_payload(
    config: AppConfig,
    account_payload: dict[str, Any],
    summary_payload: dict[str, Any] | None = None,
) -> AccountSnapshot:
    account = account_payload.get("account", {})
    summary = summary_payload.get("account", {}) if summary_payload else {}
    positions: dict[str, int] = {}
    for item in account.get("positions", []):
        instrument = item.get("instrument")
        if not instrument:
            continue
        long_units = int(float(item.get("long", {}).get("units", "0")))
        short_units = int(float(item.get("short", {}).get("units", "0")))
        positions[instrument] = long_units + short_units
    return AccountSnapshot(
        environment=config.environment,
        account_id=config.account_id,
        nav=_safe_float(summary.get("NAV") or account.get("NAV") or account.get("nav")),
        balance=_safe_float(summary.get("balance") or account.get("balance")),
        open_trade_count=int(account.get("openTradeCount", 0) or 0),
        positions_by_instrument=positions,
    )


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
