"""
Trade latency gating with hysteresis and per-mode profiles.

Purpose:
- Keep execution safe by blocking trades when stream latency/backlog is high.
- Separate observability (raw/clamped stats) from execution gating thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import os
from typing import Iterable, Tuple


@dataclass
class TradeLatencyGateConfig:
    mode: str
    instrument: str
    skew_outlier_ms: float = 1000.0
    backlog_warn_ms: float = 1500.0
    backlog_block_ms: float = 500.0
    consecutive_backlog_to_block: int = 3
    consecutive_good_to_unblock: int = 10
    outlier_high_ms: float = 10000.0
    min_samples: int = 60
    block_ms_min: float = 250.0
    block_ms_max: float = 750.0
    warn_ms_min: float = 800.0
    warn_ms_max: float = 2500.0
    effective_window_size: int = 120
    warn_p95_hyst_on_ms: float = 25.0
    warn_p95_hyst_off_ms: float = 50.0
    consecutive_p95_to_warn: int = 2
    consecutive_p95_to_clear: int = 3

    def clamp(self) -> None:
        self.backlog_block_ms = min(
            max(self.backlog_block_ms, self.block_ms_min), self.block_ms_max
        )
        self.backlog_warn_ms = min(
            max(self.backlog_warn_ms, self.warn_ms_min), self.warn_ms_max
        )


@dataclass
class TradeLatencyGateState:
    blocked: bool = True
    total_samples: int = 0
    backlog_samples: int = 0
    outlier_samples: int = 0
    skew_samples: int = 0
    consecutive_backlog: int = 0
    consecutive_good: int = 0
    last_raw_ms: float | None = None
    last_effective_ms: float | None = None
    last_backlog: bool | None = None
    last_outlier: bool | None = None
    last_skew_ms: float | None = None
    last_effective_p95_ms: float | None = None
    last_effective_mean_ms: float | None = None
    warn_p95_on_ms: float | None = None
    warn_p95_off_ms: float | None = None
    p95_warn_streak: int = 0
    p95_clear_streak: int = 0
    warn_p95_latched: bool = False


class TradeLatencyGate:
    def __init__(self, config: TradeLatencyGateConfig) -> None:
        config.clamp()
        self.config = config
        self.state = TradeLatencyGateState(blocked=True)
        self._effective_samples: list[float] = []

    def update(
        self,
        raw_ms: float | None,
        *,
        effective_ms: float | None,
        backlog: bool,
        outlier: bool,
        skew_ms: float | None,
    ) -> TradeLatencyGateState:
        if raw_ms is None and effective_ms is None:
            return self.state

        cfg = self.config
        st = self.state
        sample_ms = effective_ms if effective_ms is not None else raw_ms

        st.total_samples += 1
        st.last_raw_ms = raw_ms
        st.last_effective_ms = effective_ms
        st.last_backlog = backlog
        st.last_outlier = outlier
        st.last_skew_ms = skew_ms

        if skew_ms is not None:
            st.skew_samples += 1
        if backlog:
            st.backlog_samples += 1
        if outlier:
            st.outlier_samples += 1

        if effective_ms is not None and not outlier:
            self._effective_samples.append(effective_ms)
            if len(self._effective_samples) > self.config.effective_window_size:
                self._effective_samples = self._effective_samples[-self.config.effective_window_size :]
            eff_p95, eff_mean = self.effective_stats()
            st.last_effective_p95_ms = eff_p95
            st.last_effective_mean_ms = eff_mean
            on_threshold = self.config.backlog_warn_ms + self.config.warn_p95_hyst_on_ms
            off_threshold = max(0.0, self.config.backlog_warn_ms - self.config.warn_p95_hyst_off_ms)
            st.warn_p95_on_ms = on_threshold
            st.warn_p95_off_ms = off_threshold
            if st.total_samples >= self.config.min_samples and eff_p95 is not None:
                if eff_p95 >= on_threshold:
                    st.p95_warn_streak = min(
                        st.p95_warn_streak + 1, self.config.consecutive_p95_to_warn
                    )
                    st.p95_clear_streak = 0
                elif eff_p95 <= off_threshold:
                    st.p95_clear_streak = min(
                        st.p95_clear_streak + 1, self.config.consecutive_p95_to_clear
                    )
                    st.p95_warn_streak = 0
                # within band: keep streaks as-is
            if not st.warn_p95_latched and st.p95_warn_streak >= self.config.consecutive_p95_to_warn:
                st.warn_p95_latched = True
                st.p95_warn_streak = 0
            if st.warn_p95_latched and st.p95_clear_streak >= self.config.consecutive_p95_to_clear:
                st.warn_p95_latched = False
                st.p95_clear_streak = 0

        backlog_hit = backlog or outlier or (sample_ms is not None and sample_ms >= cfg.backlog_block_ms)
        good_hit = (not backlog) and (not outlier) and (sample_ms is not None and sample_ms < cfg.backlog_warn_ms)

        if backlog_hit:
            st.consecutive_backlog += 1
            st.consecutive_good = 0
        elif good_hit:
            st.consecutive_good += 1
            st.consecutive_backlog = 0

        # Blocking logic with hysteresis and minimum sample requirement.
        if st.total_samples < cfg.min_samples:
            st.blocked = True
        elif st.consecutive_backlog >= cfg.consecutive_backlog_to_block:
            st.blocked = True
        elif st.blocked and st.consecutive_good >= cfg.consecutive_good_to_unblock:
            st.blocked = False

        # Hard block on outlier/backlog when no good streak present.
        if backlog or outlier:
            st.blocked = True

        return st

    def should_warn(self) -> bool:
        st = self.state
        if st.last_effective_ms is not None:
            return st.last_effective_ms >= self.config.backlog_warn_ms
        return st.last_raw_ms is not None and st.last_raw_ms >= self.config.backlog_warn_ms

    def effective_stats(self) -> tuple[float | None, float | None]:
        if not self._effective_samples:
            return None, None
        values = sorted(self._effective_samples)
        mean = sum(values) / len(values)
        p95_index = max(0, int(round(0.95 * (len(values) - 1))))
        return values[p95_index], mean

    def snapshot(self) -> dict:
        warn_last = self.should_warn()
        warn_p95 = self.state.warn_p95_latched
        warn_aggregate = warn_last or warn_p95
        data = {
            **asdict(self.config),
            **asdict(self.state),
            "warn": warn_aggregate,
            "warn_last": warn_last,
            "warn_p95": warn_p95,
            "effective_p95_ms": self.state.last_effective_p95_ms,
            "effective_mean_ms": self.state.last_effective_mean_ms,
            "warn_p95_on_ms": self.state.warn_p95_on_ms,
            "warn_p95_off_ms": self.state.warn_p95_off_ms,
            "p95_warn_streak": self.state.p95_warn_streak,
            "p95_clear_streak": self.state.p95_clear_streak,
        }
        return data


def suggest_thresholds(
    raw_ms_values: Iterable[float],
    *,
    warn_min: float,
    warn_max: float,
    block_min: float,
    block_max: float,
) -> tuple[float, float]:
    values = [max(v, 0.0) for v in raw_ms_values if v is not None]
    if not values:
        return warn_min, block_min
    values.sort()
    p95_index = max(0, int(round(0.95 * (len(values) - 1))))
    p99_index = max(0, int(round(0.99 * (len(values) - 1))))
    warn = min(max(values[p95_index], warn_min), warn_max)
    block = min(max(values[p99_index], block_min), block_max)
    return warn, block


def profile_path(mode: str, instrument: str) -> str:
    safe = instrument.replace("/", "_")
    return os.path.join(
        "data", f"latency_profile_{mode.lower()}_{safe}.json"
    )


def write_profile(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def thresholds_path(mode: str, instrument: str, base_dir: str | None = None) -> str:
    safe = instrument.replace("/", "_")
    root = base_dir or "data"
    return os.path.join(root, f"latency_thresholds_{mode.lower()}_{safe}.json")


def load_thresholds(
    mode: str, instrument: str, *, base_dir: str | None = None
) -> tuple[TradeLatencyGateConfig, dict]:
    cfg = TradeLatencyGateConfig(mode=mode, instrument=instrument)
    search_paths = []
    env_dir = os.getenv("OANDA_LATENCY_THRESHOLDS_DIR")
    if env_dir:
        search_paths.append(thresholds_path(mode, instrument, base_dir=env_dir))
    search_paths.append(thresholds_path(mode, instrument, base_dir=os.path.join("config", "latency_thresholds")))
    search_paths.append(thresholds_path(mode, instrument, base_dir="data"))

    path = None
    for candidate in search_paths:
        if os.path.exists(candidate):
            path = candidate
            break

    meta = {"path": path, "source": "defaults", "sha1": None}
    if path is None:
        print("WARNING: threshold file missing, using defaults.")
        return cfg, meta
    with open(path, "r", encoding="utf-8") as handle:
        content = handle.read()
    meta["sha1"] = hashlib.sha1(content.encode("utf-8")).hexdigest()
    data = json.loads(content)
    for key, value in data.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)
    # Honor explicit thresholds from file, even if below default mins.
    cfg.warn_ms_min = 0.0
    cfg.block_ms_min = 0.0
    override = os.getenv("TG_BACKLOG_WARN_MS_OVERRIDE")
    if override:
        try:
            cfg.backlog_warn_ms = float(override)
            meta["backlog_warn_ms_override"] = cfg.backlog_warn_ms
        except ValueError:
            meta["backlog_warn_ms_override"] = "invalid"
    cfg.clamp()
    meta["source"] = "file"
    meta["path"] = path
    return cfg, meta
