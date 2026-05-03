"""
Simple latency tracker for response time monitoring.

Purpose:
- Record request/stream latency samples.
- Provide lightweight summaries for quick diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable
import csv
import json
import statistics
import time


@dataclass
class LatencySample:
    """
    Single latency measurement.
    """

    name: str
    milliseconds: float
    timestamp: float = field(default_factory=lambda: time.time())


@dataclass
class LatencyStats:
    """
    Aggregate latency statistics for a given label.
    """

    name: str
    count: int
    min_ms: float
    max_ms: float
    mean_ms: float
    p95_ms: float


class LatencyTracker:
    """
    In-memory latency tracker with simple stats.
    """

    def __init__(self) -> None:
        self._samples: list[LatencySample] = []

    def add(self, name: str, milliseconds: float) -> None:
        self._samples.append(LatencySample(name=name, milliseconds=milliseconds))

    def stats(self, name: str) -> LatencyStats:
        values = [s.milliseconds for s in self._samples if s.name == name]
        if not values:
            raise ValueError(f"No latency samples recorded for '{name}'.")
        values_sorted = sorted(values)
        p95_index = max(0, int(round(0.95 * (len(values_sorted) - 1))))
        return LatencyStats(
            name=name,
            count=len(values_sorted),
            min_ms=min(values_sorted),
            max_ms=max(values_sorted),
            mean_ms=statistics.mean(values_sorted),
            p95_ms=values_sorted[p95_index],
        )

    def all_names(self) -> Iterable[str]:
        return sorted({s.name for s in self._samples})

    def samples(self) -> list[LatencySample]:
        return list(self._samples)


def export_latency_csv(samples: list[LatencySample], path: str) -> None:
    """
    Write latency samples to CSV.
    """

    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "milliseconds", "timestamp"])
        for sample in samples:
            writer.writerow([sample.name, sample.milliseconds, sample.timestamp])


def export_latency_jsonl(samples: list[LatencySample], path: str) -> None:
    """
    Write latency samples to JSONL.
    """

    with open(path, "w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(
                json.dumps(
                    {
                        "name": sample.name,
                        "milliseconds": sample.milliseconds,
                        "timestamp": sample.timestamp,
                    }
                )
                + "\n"
            )
