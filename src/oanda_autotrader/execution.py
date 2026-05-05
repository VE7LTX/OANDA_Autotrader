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
    max_gross_position_units: int = 300
    max_currency_gross_units: int = 200
    max_currency_positions: int = 2
    min_confidence: float = 0.55
    require_stop_loss: bool = True
    time_in_force: str = "FOK"
    position_fill: str = "DEFAULT"

    def allows_instrument(self, instrument: str) -> bool:
        return not self.allowed_instruments or instrument in self.allowed_instruments

    def projected_gross_position_units(self, snapshot: AccountSnapshot, action: TradeAction) -> int:
        projected = self.project_snapshot(snapshot, action)
        return sum(abs(int(units)) for units in projected.positions_by_instrument.values() if units)

    def projected_currency_gross_units(self, snapshot: AccountSnapshot, action: TradeAction) -> int:
        projected = self.project_snapshot(snapshot, action)
        currency_units = self._currency_gross_from_positions(projected.positions_by_instrument)
        return sum(currency_units.values())

    def projected_currency_position_count(self, snapshot: AccountSnapshot, action: TradeAction) -> int:
        projected = self.project_snapshot(snapshot, action)
        currency_counts = self._currency_position_counts(projected.positions_by_instrument)
        return max(currency_counts.values(), default=0)

    @staticmethod
    def _currency_gross_from_positions(positions: dict[str, int]) -> dict[str, int]:
        exposure: dict[str, int] = {}
        for instrument, units in positions.items():
            if not units:
                continue
            currencies = _instrument_currencies(instrument)
            if currencies is None:
                continue
            base, quote = currencies
            magnitude = abs(int(units))
            exposure[base] = exposure.get(base, 0) + magnitude
            exposure[quote] = exposure.get(quote, 0) + magnitude
        return exposure

    @staticmethod
    def _currency_position_counts(positions: dict[str, int]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for instrument, units in positions.items():
            if not units:
                continue
            currencies = _instrument_currencies(instrument)
            if currencies is None:
                continue
            base, quote = currencies
            counts[base] = counts.get(base, 0) + 1
            counts[quote] = counts.get(quote, 0) + 1
        return counts

    def project_snapshot(self, snapshot: AccountSnapshot, action: TradeAction) -> AccountSnapshot:
        kind = action.action.lower()
        positions = dict(snapshot.positions_by_instrument)
        open_trade_count = int(snapshot.open_trade_count)
        if kind == "close":
            current_units = int(positions.get(action.instrument, 0) or 0)
            if current_units != 0:
                positions[action.instrument] = 0
                open_trade_count = max(0, open_trade_count - 1)
            return AccountSnapshot(
                environment=snapshot.environment,
                account_id=snapshot.account_id,
                nav=snapshot.nav,
                balance=snapshot.balance,
                open_trade_count=open_trade_count,
                positions_by_instrument=positions,
            )
        if kind in {"buy", "sell"}:
            current_units = int(positions.get(action.instrument, 0) or 0)
            if current_units == 0:
                open_trade_count += 1
                positions[action.instrument] = action.units if kind == "buy" else -action.units
            elif current_units > 0 and kind == "buy":
                positions[action.instrument] = current_units + action.units
            elif current_units < 0 and kind == "sell":
                positions[action.instrument] = current_units - action.units
            else:
                positions[action.instrument] = (
                    current_units + action.units if current_units > 0 else current_units - action.units
                )
        return AccountSnapshot(
            environment=snapshot.environment,
            account_id=snapshot.account_id,
            nav=snapshot.nav,
            balance=snapshot.balance,
            open_trade_count=open_trade_count,
            positions_by_instrument=positions,
        )


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
        if kind in {"buy", "sell"}:
            projected_gross = self.policy.projected_gross_position_units(snapshot, action)
            if projected_gross > self.policy.max_gross_position_units:
                raise ValueError("Gross position exposure limit reached.")
            projected_currency_gross = self.policy.projected_currency_gross_units(snapshot, action)
            if projected_currency_gross > self.policy.max_currency_gross_units:
                raise ValueError("Currency exposure limit reached.")
            projected_currency_positions = self.policy.projected_currency_position_count(snapshot, action)
            if projected_currency_positions > self.policy.max_currency_positions:
                raise ValueError("Currency correlation limit reached.")

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
        fill = response.get("orderFillTransaction") if isinstance(response, dict) else None
        cancel = response.get("orderCancelTransaction") if isinstance(response, dict) else None
        submitted = bool(fill)
        cancel_reason = cancel.get("reason") if isinstance(cancel, dict) else None
        return {
            "submitted": submitted,
            "dry_run": False,
            "order": order,
            "response": response,
            "status": "filled" if submitted else "canceled",
            "cancel_reason": cancel_reason,
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

    def project_snapshot(self, snapshot: AccountSnapshot, action: TradeAction) -> AccountSnapshot:
        return self.policy.project_snapshot(snapshot, action)

    def projected_gross_position_units(self, snapshot: AccountSnapshot, action: TradeAction) -> int:
        return self.policy.projected_gross_position_units(snapshot, action)

    def projected_currency_gross_units(self, snapshot: AccountSnapshot, action: TradeAction) -> int:
        return self.policy.projected_currency_gross_units(snapshot, action)


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


def _instrument_currencies(instrument: str) -> tuple[str, str] | None:
    parts = str(instrument or "").split("_", 1)
    if len(parts) != 2:
        return None
    base, quote = parts
    if len(base) != 3 or len(quote) != 3:
        return None
    return base, quote
