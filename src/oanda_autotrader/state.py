"""
Local bot runtime state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
import time


@dataclass
class BotState:
    consecutive_failures: int = 0
    last_trade_ts: float | None = None
    last_action: str | None = None
    current_position: dict | None = None
    realized_pnl_day: float = 0.0
    realized_pnl_week: float = 0.0
    last_day_reset: str = field(default_factory=lambda: _today_utc())
    last_week_reset: str = field(default_factory=lambda: _week_utc())

    def can_trade(self, cooldown_seconds: int) -> bool:
        if self.last_trade_ts is None:
            return True
        return (time.time() - self.last_trade_ts) >= cooldown_seconds

    def remaining_cooldown(self, cooldown_seconds: int) -> int:
        if self.last_trade_ts is None:
            return 0
        remaining = cooldown_seconds - (time.time() - self.last_trade_ts)
        return max(0, int(remaining))

    def mark_failure(self) -> None:
        self.consecutive_failures += 1

    def mark_success(self, *, traded: bool, action: str | None = None) -> None:
        self.consecutive_failures = 0
        if traded:
            self.last_trade_ts = time.time()
        if action:
            self.last_action = action

    def refresh_periods(self) -> None:
        if self.last_day_reset != _today_utc():
            self.realized_pnl_day = 0.0
            self.last_day_reset = _today_utc()
        if self.last_week_reset != _week_utc():
            self.realized_pnl_week = 0.0
            self.last_week_reset = _week_utc()

    def open_trade(
        self,
        *,
        side: str,
        units: int,
        entry_price: float,
        instrument: str,
        opened_at_time: str | None = None,
    ) -> None:
        self.current_position = {
            "side": side,
            "units": units,
            "entry_price": entry_price,
            "instrument": instrument,
            "opened_at": time.time(),
            "opened_at_time": opened_at_time,
            "peak_price": entry_price,
            "trough_price": entry_price,
        }

    def close_trade(self, *, exit_price: float) -> float | None:
        if not self.current_position:
            return None
        side = str(self.current_position["side"])
        units = int(self.current_position["units"])
        entry = float(self.current_position["entry_price"])
        pnl = (exit_price - entry) * units if side == "long" else (entry - exit_price) * units
        self.realized_pnl_day += pnl
        self.realized_pnl_week += pnl
        self.current_position = None
        return pnl

    def update_trade_markers(self, price: float) -> None:
        if not self.current_position:
            return
        side = str(self.current_position["side"])
        peak = float(self.current_position.get("peak_price", price))
        trough = float(self.current_position.get("trough_price", price))
        if side == "long":
            self.current_position["peak_price"] = max(peak, price)
            self.current_position["trough_price"] = min(trough, price)
        else:
            self.current_position["peak_price"] = min(peak, price)
            self.current_position["trough_price"] = max(trough, price)

    def save(self, path: str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(asdict(self)), encoding="utf-8")

    @classmethod
    def load(cls, path: str) -> "BotState":
        target = Path(path)
        if not target.exists():
            return cls()
        payload = json.loads(target.read_text(encoding="utf-8"))
        return cls(
            consecutive_failures=int(payload.get("consecutive_failures", 0) or 0),
            last_trade_ts=payload.get("last_trade_ts"),
            last_action=payload.get("last_action"),
            current_position=payload.get("current_position"),
            realized_pnl_day=float(payload.get("realized_pnl_day", 0.0) or 0.0),
            realized_pnl_week=float(payload.get("realized_pnl_week", 0.0) or 0.0),
            last_day_reset=str(payload.get("last_day_reset") or _today_utc()),
            last_week_reset=str(payload.get("last_week_reset") or _week_utc()),
        )


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _week_utc() -> str:
    now = datetime.now(timezone.utc).isocalendar()
    return f"{now.year}-W{now.week:02d}"
