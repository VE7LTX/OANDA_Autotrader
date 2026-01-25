"""
Minimal models for streaming messages.

Purpose:
- Provide typed views of streaming payloads for easier validation.
- Keep parsing lightweight and non-blocking.

Notes:
- We keep raw payloads for forward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StreamMessage:
    """
    Base streaming message with raw payload.
    """

    type: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class PriceMessage(StreamMessage):
    instrument: str | None
    time: str | None


@dataclass(frozen=True)
class TransactionMessage(StreamMessage):
    transaction_id: str | None
    account_id: str | None


@dataclass(frozen=True)
class HeartbeatMessage(StreamMessage):
    time: str | None


def parse_stream_message(payload: dict[str, Any]) -> StreamMessage:
    """
    Parse a raw payload into a typed StreamMessage.
    """

    msg_type = str(payload.get("type", "UNKNOWN"))
    if msg_type == "PRICE":
        return PriceMessage(
            type=msg_type,
            raw=payload,
            instrument=payload.get("instrument"),
            time=payload.get("time"),
        )
    if msg_type == "TRANSACTION":
        return TransactionMessage(
            type=msg_type,
            raw=payload,
            transaction_id=payload.get("id"),
            account_id=payload.get("accountID"),
        )
    if msg_type == "HEARTBEAT":
        return HeartbeatMessage(
            type=msg_type,
            raw=payload,
            time=payload.get("time"),
        )
    return StreamMessage(type=msg_type, raw=payload)
