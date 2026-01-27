"""
Retrain gating helpers for live accuracy + pipeline freshness.

Keeps training decisions robust to partial/invalid JSONL lines.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


@dataclass
class RetrainGateDecision:
    allow: bool
    reason: str
    coverage: float | None
    mae: float | None
    mae_threshold: float | None
    window_n: int
    fields_used: list[str]
    blocked: bool
    stale: bool
    details: dict[str, Any]


def _parse_iso(ts: str | None) -> float | None:
    if not ts:
        return None
    raw = ts.strip()
    if raw.endswith("Z"):
        raw = raw[:-1]
    if "." in raw:
        head, frac = raw.split(".", 1)
        frac = frac[:6].ljust(6, "0")
        raw = f"{head}.{frac}"
    try:
        dt = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def read_last_jsonl(path: str, limit: int) -> list[dict]:
    if not os.path.exists(path):
        return []
    records: list[dict] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records[-limit:]


def is_file_stale(path: str, max_age_s: float) -> bool:
    if not os.path.exists(path):
        return True
    mtime = os.path.getmtime(path)
    age = time.time() - mtime
    return age > max_age_s


def latest_candle_age(candles_dir: str, pattern: str) -> float | None:
    files = sorted(
        Path(candles_dir).glob(f"{pattern}*.jsonl"),
        key=lambda p: p.stat().st_mtime,
    )
    if not files:
        return None
    last_line = _last_json_line(str(files[-1]))
    if not last_line:
        return None
    ts = _parse_iso(last_line.get("time"))
    if ts is None:
        return None
    return max(0.0, time.time() - ts)


def _last_json_line(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        if size == 0:
            return None
        chunk = min(size, 65536)
        handle.seek(-chunk, os.SEEK_END)
        data = handle.read().decode("utf-8", errors="ignore")
    lines = [line for line in data.splitlines() if line.strip()]
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return None


def read_trade_gate_blocked(monitor_path: str) -> bool:
    last = _last_json_line(monitor_path)
    if not last:
        return False
    gate = last.get("trade_gate")
    if gate is None:
        gate = (last.get("rest") or {}).get("trade_gate") or {}
    return bool((gate or {}).get("blocked"))


def compute_score_metrics(records: list[dict]) -> tuple[float | None, float | None, list[str]]:
    if not records:
        return None, None, []
    mae_values: list[float] = []
    abs_moves: list[float] = []
    fields_used: set[str] = set()

    for rec in records:
        if isinstance(rec.get("mae"), (int, float)):
            mae_values.append(float(rec["mae"]))
            fields_used.add("mae")
        elif isinstance(rec.get("mean_abs_error"), (int, float)):
            mae_values.append(float(rec["mean_abs_error"]))
            fields_used.add("mean_abs_error")
        else:
            results = rec.get("results") or []
            diffs: list[float] = []
            for item in results:
                actual = item.get("actual")
                pred = item.get("predicted") or item.get("mean") or item.get("forecast")
                if isinstance(actual, (int, float)) and isinstance(pred, (int, float)):
                    diffs.append(abs(float(actual) - float(pred)))
            if diffs:
                mae_values.append(sum(diffs) / len(diffs))
                fields_used.add("results_actual_pred")

        results = rec.get("results") or []
        for item in results:
            actual = item.get("actual")
            prev = item.get("prev") or item.get("baseline")
            if isinstance(actual, (int, float)) and isinstance(prev, (int, float)):
                abs_moves.append(abs(float(actual) - float(prev)))
                fields_used.add("results_actual_prev")

    mae = sum(mae_values) / len(mae_values) if mae_values else None
    median_abs_move = median(abs_moves) if abs_moves else None
    return mae, median_abs_move, sorted(fields_used)


def evaluate_retrain_gate(
    *,
    scores_path: str,
    monitor_path: str,
    predictions_path: str,
    candles_dir: str,
    candles_pattern: str,
    window_n: int,
    min_coverage: float,
    fixed_mae_threshold: float,
    volatility_scale: float,
    stale_monitor_s: float,
    stale_pred_s: float,
    stale_score_s: float,
    stale_candle_s: float,
) -> RetrainGateDecision:
    records = read_last_jsonl(scores_path, window_n)
    mae, median_abs_move, fields_used = compute_score_metrics(records)
    coverage = len(records) / max(window_n, 1) if records else None

    monitor_stale = is_file_stale(monitor_path, stale_monitor_s)
    pred_stale = is_file_stale(predictions_path, stale_pred_s)
    scores_stale = is_file_stale(scores_path, stale_score_s)
    stale = monitor_stale or pred_stale or scores_stale
    candle_age = latest_candle_age(candles_dir, candles_pattern)
    if candle_age is None or candle_age > stale_candle_s:
        stale = True

    blocked = read_trade_gate_blocked(monitor_path)

    if pred_stale and not monitor_stale and not blocked and (coverage is None or scores_stale):
        return RetrainGateDecision(
            allow=True,
            reason="bootstrap_pred",
            coverage=coverage or 0.0,
            mae=mae,
            mae_threshold=None,
            window_n=len(records),
            fields_used=fields_used,
            blocked=blocked,
            stale=stale,
            details={
                "records": len(records),
                "candle_age_s": candle_age,
                "monitor_stale": monitor_stale,
                "pred_stale": pred_stale,
                "scores_stale": scores_stale,
            },
        )

    if coverage is None:
        return RetrainGateDecision(
            allow=False,
            reason="no_scores",
            coverage=0.0,
            mae=None,
            mae_threshold=None,
            window_n=window_n,
            fields_used=fields_used,
            blocked=blocked,
            stale=stale,
            details={
                "records": len(records),
                "candle_age_s": candle_age,
                "monitor_stale": monitor_stale,
                "pred_stale": pred_stale,
                "scores_stale": scores_stale,
            },
        )

    if stale:
        return RetrainGateDecision(
            allow=False,
            reason="stale_pipeline",
            coverage=coverage,
            mae=mae,
            mae_threshold=None,
            window_n=len(records),
            fields_used=fields_used,
            blocked=blocked,
            stale=stale,
            details={
                "records": len(records),
                "candle_age_s": candle_age,
                "monitor_stale": monitor_stale,
                "pred_stale": pred_stale,
                "scores_stale": scores_stale,
            },
        )

    if blocked:
        return RetrainGateDecision(
            allow=False,
            reason="trade_gate_blocked",
            coverage=coverage,
            mae=mae,
            mae_threshold=None,
            window_n=len(records),
            fields_used=fields_used,
            blocked=blocked,
            stale=stale,
            details={
                "records": len(records),
                "candle_age_s": candle_age,
                "monitor_stale": monitor_stale,
                "pred_stale": pred_stale,
                "scores_stale": scores_stale,
            },
        )

    if coverage < min_coverage:
        return RetrainGateDecision(
            allow=True,
            reason="low_coverage",
            coverage=coverage,
            mae=mae,
            mae_threshold=None,
            window_n=len(records),
            fields_used=fields_used,
            blocked=blocked,
            stale=stale,
            details={
                "records": len(records),
                "candle_age_s": candle_age,
                "monitor_stale": monitor_stale,
                "pred_stale": pred_stale,
                "scores_stale": scores_stale,
            },
        )

    mae_threshold = (
        median_abs_move * volatility_scale if median_abs_move is not None else fixed_mae_threshold
    )
    if mae is not None and mae > mae_threshold:
        return RetrainGateDecision(
            allow=True,
            reason="mae_high",
            coverage=coverage,
            mae=mae,
            mae_threshold=mae_threshold,
            window_n=len(records),
            fields_used=fields_used,
            blocked=blocked,
            stale=stale,
            details={
                "records": len(records),
                "candle_age_s": candle_age,
                "monitor_stale": monitor_stale,
                "pred_stale": pred_stale,
                "scores_stale": scores_stale,
            },
        )

    return RetrainGateDecision(
        allow=False,
        reason="metrics_ok",
        coverage=coverage,
        mae=mae,
        mae_threshold=mae_threshold,
        window_n=len(records),
        fields_used=fields_used,
        blocked=blocked,
        stale=stale,
        details={
            "records": len(records),
            "candle_age_s": candle_age,
            "monitor_stale": monitor_stale,
            "pred_stale": pred_stale,
            "scores_stale": scores_stale,
        },
    )
