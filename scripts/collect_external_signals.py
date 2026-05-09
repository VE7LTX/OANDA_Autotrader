from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


POLYMARKET_GAMMA = "https://gamma-api.polymarket.com"
SANTIMENT_GRAPHQL = "https://api.santiment.net/graphql"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect external context signals into scanner format.")
    parser.add_argument("--config", default="external_signal_sources.example.json")
    parser.add_argument("--output", default="data/external_signals.json")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--skip-polymarket", action="store_true")
    parser.add_argument("--skip-santiment", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
    generated_at = datetime.now(timezone.utc).isoformat()
    signals: list[dict[str, Any]] = []
    signals.extend(normalize_manual_signals(config.get("manual") or [], generated_at))
    if not args.skip_polymarket:
        signals.extend(collect_polymarket_signals(config.get("polymarket") or [], generated_at, args.timeout))
    if not args.skip_santiment:
        signals.extend(collect_santiment_signals(config.get("santiment") or [], generated_at, args.timeout))

    payload = {"generated_at": generated_at, "signals": signals}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {len(signals)} signals to {output}")


def normalize_manual_signals(items: list[Any], generated_at: str) -> list[dict[str, Any]]:
    signals = []
    for item in items:
        if not isinstance(item, dict):
            continue
        signal = dict(item)
        signal.setdefault("source", "manual")
        signal.setdefault("timestamp", generated_at)
        if signal.get("instrument") or signal.get("instruments"):
            signals.append(signal)
    return signals


def collect_polymarket_signals(items: list[Any], generated_at: str, timeout: float) -> list[dict[str, Any]]:
    signals = []
    for item in items:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug") or "").strip()
        instrument = str(item.get("instrument") or "").strip().upper()
        if not slug or not instrument:
            continue
        try:
            markets = fetch_polymarket_markets(slug, str(item.get("kind") or "event"), timeout)
        except requests.RequestException as exc:
            signals.append(error_signal("polymarket", instrument, generated_at, slug, exc))
            continue
        for market in markets:
            probability = polymarket_yes_probability(market)
            signal = polymarket_signal_from_probability(item, market, probability, generated_at)
            if signal is not None:
                signals.append(signal)
    return signals


def fetch_polymarket_markets(slug: str, kind: str, timeout: float) -> list[dict[str, Any]]:
    if kind.lower() == "market":
        response = requests.get(f"{POLYMARKET_GAMMA}/markets", params={"slug": slug}, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []
    response = requests.get(f"{POLYMARKET_GAMMA}/events", params={"slug": slug}, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    events = payload if isinstance(payload, list) else []
    markets: list[dict[str, Any]] = []
    for event in events:
        if isinstance(event, dict):
            markets.extend(m for m in (event.get("markets") or []) if isinstance(m, dict))
    return markets


def polymarket_signal_from_probability(
    config: dict[str, Any],
    market: dict[str, Any],
    probability: float | None,
    generated_at: str,
) -> dict[str, Any] | None:
    if probability is None:
        return None
    threshold = float(config.get("threshold", 0.58) or 0.58)
    direction = None
    if probability >= threshold:
        direction = config.get("yes_direction")
        confidence = min(1.0, max(0.0, (probability - 0.5) * 2.0))
    elif probability <= 1.0 - threshold:
        direction = config.get("no_direction")
        confidence = min(1.0, max(0.0, (0.5 - probability) * 2.0))
    else:
        return None
    if not direction:
        return None
    return {
        "source": "polymarket",
        "instrument": str(config.get("instrument") or "").upper(),
        "direction": direction,
        "confidence": confidence,
        "probability": probability,
        "market": market.get("question") or market.get("slug") or config.get("slug"),
        "reason": config.get("reason") or "Polymarket probability threshold crossed.",
        "timestamp": generated_at,
    }


def polymarket_yes_probability(market: dict[str, Any]) -> float | None:
    outcomes = parse_jsonish_list(market.get("outcomes"))
    prices = parse_jsonish_list(market.get("outcomePrices"))
    if outcomes and prices and len(outcomes) == len(prices):
        for outcome, price in zip(outcomes, prices):
            if str(outcome).strip().lower() == "yes":
                return safe_probability(price)
    for key in ("lastTradePrice", "bestBid", "bestAsk"):
        value = safe_probability(market.get(key))
        if value is not None:
            return value
    return None


def collect_santiment_signals(items: list[Any], generated_at: str, timeout: float) -> list[dict[str, Any]]:
    token = os.getenv("SANTIMENT_API_KEY") or os.getenv("SANAPI_KEY")
    if not token:
        return []
    signals = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            points = fetch_santiment_metric(item, token, timeout)
        except requests.RequestException as exc:
            signals.append(error_signal("santiment", str(item.get("instrument") or "").upper(), generated_at, item.get("metric"), exc))
            continue
        signal = santiment_signal_from_points(item, points, generated_at)
        if signal is not None:
            signals.append(signal)
    return signals


def fetch_santiment_metric(config: dict[str, Any], token: str, timeout: float) -> list[dict[str, Any]]:
    lookback_hours = int(config.get("lookback_hours", 24) or 24)
    to_time = datetime.now(timezone.utc)
    from_time = to_time - timedelta(hours=max(2, lookback_hours))
    query = """
    query($metric: String!, $slug: String!, $from: DateTime!, $to: DateTime!, $interval: interval!) {
      getMetric(metric: $metric) {
        timeseriesDataJson(selector: { slug: $slug }, from: $from, to: $to, interval: $interval)
      }
    }
    """
    variables = {
        "metric": str(config.get("metric") or "social_volume_total"),
        "slug": str(config.get("slug") or ""),
        "from": from_time.isoformat(),
        "to": to_time.isoformat(),
        "interval": str(config.get("interval") or "1h"),
    }
    response = requests.post(
        SANTIMENT_GRAPHQL,
        headers={"Authorization": f"Apikey {token}"},
        json={"query": query, "variables": variables},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    rows = (((payload.get("data") or {}).get("getMetric") or {}).get("timeseriesDataJson") or [])
    return rows if isinstance(rows, list) else []


def santiment_signal_from_points(
    config: dict[str, Any],
    points: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any] | None:
    values = [float(row["value"]) for row in points if isinstance(row, dict) and is_number(row.get("value"))]
    if len(values) < 3:
        return None
    previous = sum(values[:-1]) / max(1, len(values) - 1)
    latest = values[-1]
    if previous <= 0:
        return None
    change = (latest - previous) / previous
    threshold = abs(float(config.get("change_threshold", 0.15) or 0.15))
    if abs(change) < threshold:
        return None
    direction = config.get("rising_direction") if change > 0 else config.get("falling_direction")
    if not direction:
        return None
    return {
        "source": "santiment",
        "instrument": str(config.get("instrument") or "").upper(),
        "direction": direction,
        "confidence": min(1.0, abs(change)),
        "metric": config.get("metric"),
        "asset": config.get("slug"),
        "reason": config.get("reason") or "Santiment metric changed beyond threshold.",
        "timestamp": generated_at,
    }


def error_signal(source: str, instrument: str, generated_at: str, label: Any, exc: Exception) -> dict[str, Any]:
    return {
        "source": source,
        "instrument": instrument,
        "direction": "neutral",
        "confidence": 0.0,
        "reason": f"{label}: {type(exc).__name__}",
        "timestamp": generated_at,
    }


def parse_jsonish_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def safe_probability(value: Any) -> float | None:
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None
    if 0.0 <= probability <= 1.0:
        return probability
    return None


def is_number(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


if __name__ == "__main__":
    main()
