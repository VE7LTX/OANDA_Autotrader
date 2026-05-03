"""
Simple deterministic bot loop for practice trading.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import time

from .app import build_account_client, build_instruments_client
from .config import AppConfig
from .execution import PracticeExecutionEngine, RiskPolicy, snapshot_from_account_payload
from .health import HealthConfig, evaluate_bot_health
from .indicators import atr
from .state import BotState
from .strategy import StrategyConfig, moving_average_crossover
from .execution import TradeAction


@dataclass(frozen=True)
class BotConfig:
    instrument: str = "USD_CAD"
    granularity: str = "M5"
    candle_count: int = 120
    cooldown_seconds: int = 300
    audit_path: str = "data/bot_audit.jsonl"
    state_path: str = "data/bot_state.json"
    failure_backoff_seconds: int = 600


class SimpleTradingBot:
    def __init__(
        self,
        app_config: AppConfig,
        *,
        bot_config: BotConfig,
        strategy_config: StrategyConfig,
        risk_policy: RiskPolicy,
        health_config: HealthConfig,
        state: BotState | None = None,
    ) -> None:
        self.app_config = app_config
        self.bot_config = bot_config
        self.strategy_config = strategy_config
        self.risk_policy = risk_policy
        self.health_config = health_config
        self.state = state or BotState.load(bot_config.state_path)
        self.account_client = build_account_client(app_config)
        self.instruments_client = build_instruments_client(app_config)
        self.execution_engine = PracticeExecutionEngine(app_config, risk_policy)

    def run_cycle(self, *, dry_run: bool = True) -> dict[str, Any]:
        record: dict[str, Any] = {
            "instrument": self.bot_config.instrument,
            "granularity": self.bot_config.granularity,
            "environment": self.app_config.environment,
            "dry_run": dry_run,
            "timestamp": int(time.time()),
        }
        try:
            self.state.refresh_periods()
            summary = self.account_client.get_account_summary(self.app_config.account_id)
            details = self.account_client.get_account(self.app_config.account_id)
            candles_payload = self.instruments_client.get_candles(
                self.bot_config.instrument,
                price="M",
                granularity=self.bot_config.granularity,
                count=self.bot_config.candle_count,
            )
            candles = candles_payload.get("candles", [])
            snapshot = snapshot_from_account_payload(self.app_config, details, summary)
            action = moving_average_crossover(candles, self.strategy_config, snapshot)
            latest_close = float((candles[-1].get("mid") or {}).get("c")) if candles else None
            latest_candle_time = candles[-1].get("time") if candles else None
            latest_atr = None
            regime_score = None
            try:
                latest_atr = atr(candles, self.strategy_config.atr_period)
            except ValueError:
                pass
            if action.metadata:
                regime_score = action.metadata.get("regime_score")
            if latest_close is not None:
                self.state.update_trade_markers(latest_close)
                managed_action = self._manage_open_position(
                    latest_close=latest_close,
                    latest_atr=latest_atr,
                    candle_time=latest_candle_time,
                )
                if managed_action is not None:
                    action = managed_action
            record["action"] = action.__dict__
            record["snapshot"] = asdict(snapshot)

            if self.state.consecutive_failures > 0 and not self.state.can_trade(
                self.bot_config.failure_backoff_seconds
            ):
                record["blocked"] = ["failure_backoff_active"]
                record["backoff_remaining_seconds"] = self.state.remaining_cooldown(
                    self.bot_config.failure_backoff_seconds
                )
                self._write_audit(record)
                return record

            if not self.state.can_trade(self.bot_config.cooldown_seconds):
                record["blocked"] = ["cooldown_active"]
                record["cooldown_remaining_seconds"] = self.state.remaining_cooldown(
                    self.bot_config.cooldown_seconds
                )
                self._write_audit(record)
                return record

            health = evaluate_bot_health(
                candles=candles,
                snapshot=snapshot,
                action=action,
                policy=self.risk_policy,
                failure_count=self.state.consecutive_failures,
                config=self.health_config,
                latest_atr=latest_atr,
                daily_pnl=self.state.realized_pnl_day,
                weekly_pnl=self.state.realized_pnl_week,
                regime_score=float(regime_score) if regime_score is not None else None,
            )
            record["health"] = asdict(health)
            if not health.ok:
                record["blocked"] = health.reasons
                self.state.save(self.bot_config.state_path)
                self._write_audit(record)
                return record

            result = self.execution_engine.execute(action, snapshot, dry_run=dry_run)
            record["result"] = result
            if latest_close is not None:
                realized = self._update_local_position(
                    action.action.lower(),
                    latest_close,
                    latest_candle_time,
                    action.units,
                )
                if realized is not None:
                    record["realized_pnl"] = realized
            traded = bool(result.get("submitted")) or (
                action.action.lower() in {"buy", "sell", "close"} and not dry_run
            )
            self.state.mark_success(traded=traded, action=action.action.lower())
            self.state.save(self.bot_config.state_path)
            self._write_audit(record)
            return record
        except Exception as exc:
            self.state.mark_failure()
            self.state.last_trade_ts = time.time()
            self.state.save(self.bot_config.state_path)
            record["error"] = str(exc)
            self._write_audit(record)
            raise

    def _update_local_position(
        self,
        action: str,
        latest_close: float,
        candle_time: str | None,
        units: int,
    ) -> float | None:
        if action == "buy" and self.state.current_position is None:
            self.state.open_trade(
                side="long",
                units=units or self.strategy_config.units,
                entry_price=latest_close,
                instrument=self.bot_config.instrument,
                opened_at_time=candle_time,
            )
            return None
        if action == "sell" and self.state.current_position is None:
            self.state.open_trade(
                side="short",
                units=units or self.strategy_config.units,
                entry_price=latest_close,
                instrument=self.bot_config.instrument,
                opened_at_time=candle_time,
            )
            return None
        if action == "close":
            return self.state.close_trade(exit_price=latest_close)
        return None

    def _manage_open_position(
        self, *, latest_close: float, latest_atr: float | None, candle_time: str | None
    ):
        position = self.state.current_position
        if not position or latest_atr is None:
            return None
        side = str(position["side"])
        entry_price = float(position.get("entry_price", latest_close))
        peak = float(position.get("peak_price", latest_close))
        trough = float(position.get("trough_price", latest_close))
        if side == "long":
            if (
                peak - entry_price >= latest_atr * self.strategy_config.break_even_atr_multiple
                and latest_close <= entry_price
            ):
                return self._managed_close("long_break_even_exit", entry_price)
            trailing_stop = peak - (latest_atr * self.strategy_config.trailing_atr_multiple)
            if latest_close <= trailing_stop:
                return self._managed_close("long_trailing_exit", trailing_stop)
        else:
            if (
                entry_price - trough >= latest_atr * self.strategy_config.break_even_atr_multiple
                and latest_close >= entry_price
            ):
                return self._managed_close("short_break_even_exit", entry_price)
            trailing_stop = trough + (latest_atr * self.strategy_config.trailing_atr_multiple)
            if latest_close >= trailing_stop:
                return self._managed_close("short_trailing_exit", trailing_stop)

        if candle_time:
            hold_candles = self._held_candles(position, candle_time)
            if hold_candles >= self.strategy_config.max_hold_candles:
                return self._managed_close("max_hold_exit", latest_close)
        return None

    def _held_candles(self, position: dict, candle_time: str) -> int:
        try:
            current = datetime.fromisoformat(str(candle_time).replace("Z", "+00:00")).astimezone(timezone.utc)
            opened_at_time = position.get("opened_at_time")
            if opened_at_time:
                opened = datetime.fromisoformat(str(opened_at_time).replace("Z", "+00:00")).astimezone(
                    timezone.utc
                )
            else:
                opened_at = float(position.get("opened_at", time.time()))
                opened = datetime.fromtimestamp(opened_at, tz=timezone.utc)
        except Exception:
            return 0
        minutes = max(0.0, (current - opened).total_seconds() / 60.0)
        return int(minutes / max(1, self._granularity_minutes()))

    def _granularity_minutes(self) -> int:
        value = self.bot_config.granularity.upper()
        if value.startswith("M"):
            return max(1, int(value[1:]))
        if value.startswith("H"):
            return max(1, int(value[1:])) * 60
        if value == "D":
            return 24 * 60
        return 5

    def _managed_close(self, reason: str, reference: float):
        return TradeAction(
            action="close",
            instrument=self.bot_config.instrument,
            confidence=0.7,
            reason=reason,
            metadata={"managed_exit_reference": reference},
        )

    def _write_audit(self, record: dict[str, Any]) -> None:
        path = Path(self.bot_config.audit_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
