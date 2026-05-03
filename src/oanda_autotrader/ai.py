"""
Decision contracts for AI-driven practice trading experiments.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol
import json

from .execution import TradeAction


@dataclass(frozen=True)
class MarketContext:
    account: dict[str, Any]
    summary: dict[str, Any]
    candles: list[dict[str, Any]]
    instrument: str
    granularity: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_prompt_payload(self) -> dict[str, Any]:
        return asdict(self)


class DecisionProvider(Protocol):
    def decide(self, context: MarketContext) -> TradeAction:
        ...


class JsonFileDecisionProvider:
    """
    Reads one TradeAction-shaped JSON document from disk.
    Useful for driving the engine from an external AI process.
    """

    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def decide(self, context: MarketContext) -> TradeAction:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return trade_action_from_dict(payload)


class HeuristicDecisionProvider:
    """
    Minimal baseline strategy for dry-run validation.
    """

    def __init__(self, *, units: int = 100, min_move: float = 0.0003) -> None:
        self.units = units
        self.min_move = min_move

    def decide(self, context: MarketContext) -> TradeAction:
        closes = _extract_closes(context.candles)
        if len(closes) < 5:
            return TradeAction(
                action="hold",
                instrument=context.instrument,
                reason="not_enough_candles",
            )
        move = closes[-1] - closes[0]
        stop_distance = abs(move) / 2 if move else self.min_move
        if move >= self.min_move:
            return TradeAction(
                action="buy",
                instrument=context.instrument,
                units=self.units,
                confidence=0.6,
                reason="simple_momentum_up",
                stop_loss_price=f"{closes[-1] - stop_distance:.5f}",
                take_profit_price=f"{closes[-1] + stop_distance * 2:.5f}",
            )
        if move <= -self.min_move:
            return TradeAction(
                action="sell",
                instrument=context.instrument,
                units=self.units,
                confidence=0.6,
                reason="simple_momentum_down",
                stop_loss_price=f"{closes[-1] + stop_distance:.5f}",
                take_profit_price=f"{closes[-1] - stop_distance * 2:.5f}",
            )
        return TradeAction(
            action="hold",
            instrument=context.instrument,
            reason="range_bound",
        )


def trade_action_from_dict(payload: dict[str, Any]) -> TradeAction:
    return TradeAction(
        action=str(payload.get("action", "hold")),
        instrument=str(payload.get("instrument", "")),
        units=int(payload.get("units", 0) or 0),
        confidence=float(payload.get("confidence", 0.0) or 0.0),
        reason=str(payload.get("reason", "")),
        stop_loss_price=_maybe_string(payload.get("stop_loss_price")),
        take_profit_price=_maybe_string(payload.get("take_profit_price")),
        metadata=payload.get("metadata") or {},
    )


def _extract_closes(candles: list[dict[str, Any]]) -> list[float]:
    closes: list[float] = []
    for candle in candles:
        mid = candle.get("mid") or {}
        close = mid.get("c")
        if close is None:
            continue
        closes.append(float(close))
    return closes


def _maybe_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
