from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


POLYMARKET_GAMMA = "https://gamma-api.polymarket.com"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect external context signals into scanner format.")
    parser.add_argument("--config", default="external_signal_sources.example.json")
    parser.add_argument("--output", default="data/external_signals.json")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--skip-polymarket", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
    generated_at = datetime.now(timezone.utc).isoformat()
    signals: list[dict[str, Any]] = []
    signals.extend(normalize_manual_signals(config.get("manual") or [], generated_at))
    signals.extend(collect_oanda_signals(config.get("oanda") or [], generated_at))
    if not args.skip_polymarket:
        signals.extend(collect_polymarket_signals(config.get("polymarket") or [], generated_at, args.timeout))

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


def collect_oanda_signals(items: list[Any], generated_at: str) -> list[dict[str, Any]]:
    signals = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path_value = item.get("path")
        if path_value:
            signals.extend(load_oanda_signal_file(Path(str(path_value)), item, generated_at))
        else:
            signal = normalize_oanda_signal(item, item, generated_at)
            if signal is not None:
                signals.append(signal)
    return signals


def load_oanda_signal_file(path: Path, defaults: dict[str, Any], generated_at: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    else:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        rows = payload.get("signals") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            rows = []
    signals = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        signal = normalize_oanda_signal(row, defaults, generated_at)
        if signal is not None:
            signals.append(signal)
    return signals


def normalize_oanda_signal(row: dict[str, Any], defaults: dict[str, Any], generated_at: str) -> dict[str, Any] | None:
    instrument = normalize_instrument(
        first_present(row, "instrument", "symbol", "pair", "asset")
        or first_present(defaults, "instrument", "symbol", "pair", "asset")
    )
    if not instrument:
        return None
    direction = normalize_direction(
        first_present(row, "direction", "bias", "action", "signal", "side")
        or first_present(defaults, "direction", "bias", "action", "signal", "side")
    )
    if not direction:
        direction = direction_from_prices(row)
    if not direction:
        return None
    confidence = normalize_confidence(
        first_present(row, "confidence", "probability", "quality", "score")
        or first_present(defaults, "confidence", "probability", "quality", "score")
    )
    timestamp = (
        first_present(row, "timestamp", "time", "generated_at", "created_at")
        or first_present(defaults, "timestamp", "time", "generated_at", "created_at")
        or generated_at
    )
    return {
        "source": str(first_present(row, "source") or defaults.get("source") or "oanda_autochartist"),
        "instrument": instrument,
        "direction": direction,
        "confidence": confidence if confidence is not None else 0.5,
        "pattern": first_present(row, "pattern", "formation", "type"),
        "market": first_present(row, "market", "title", "name"),
        "reason": first_present(row, "reason", "description", "comment") or defaults.get("reason") or "OANDA Technical Analysis / Autochartist signal.",
        "timestamp": timestamp,
    }


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


def first_present(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            return value
    return None


def normalize_instrument(value: Any) -> str:
    text = str(value or "").strip().upper().replace("/", "_").replace("-", "_")
    if len(text) == 6 and "_" not in text:
        text = f"{text[:3]}_{text[3:]}"
    return text


def normalize_direction(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"buy", "long", "bull", "bullish", "up", "breakout_up", "resistance_break"}:
        return "bullish"
    if text in {"sell", "short", "bear", "bearish", "down", "breakout_down", "support_break"}:
        return "bearish"
    return ""


def normalize_confidence(value: Any) -> float | None:
    try:
        number = float(str(value).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None
    if number > 1.0:
        number /= 100.0
    return max(0.0, min(1.0, number))


def direction_from_prices(row: dict[str, Any]) -> str:
    target = number_from_row(row, "target", "target_price", "forecast_price", "projected_price")
    entry = number_from_row(row, "entry", "entry_price", "current_price", "price")
    if target is None or entry is None or target == entry:
        return ""
    return "bullish" if target > entry else "bearish"


def number_from_row(row: dict[str, Any], *keys: str) -> float | None:
    value = first_present(row, *keys)
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    main()
