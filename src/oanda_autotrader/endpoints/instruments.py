"""
Instrument endpoints (v20).

Source:
- OANDA v20 REST API docs (Instruments endpoints).

Included routes:
- GET /v3/instruments/{instrument}/candles

Logic flow (per method):
1) Build path with instrument name.
2) Assemble query params (price, granularity, count, time range, etc.).
3) Delegate HTTP call to OandaHttpClient and return raw JSON.
"""

from __future__ import annotations

from typing import Any

from ..http import OandaHttpClient


class InstrumentsAPI:
    """
    Endpoint grouping for instrument-related routes.
    """

    def __init__(self, client: OandaHttpClient) -> None:
        self._client = client

    def get_candles(
        self,
        instrument: str,
        *,
        price: str | None = None,
        granularity: str | None = None,
        count: int | None = None,
        time_from: str | None = None,
        time_to: str | None = None,
        smooth: bool | None = None,
        include_first: bool | None = None,
        daily_alignment: int | None = None,
        alignment_timezone: str | None = None,
        weekly_alignment: str | None = None,
        accept_datetime_format: str | None = None,
    ) -> dict[str, Any]:
        """
        GET /v3/instruments/{instrument}/candles
        """

        path = f"/v3/instruments/{instrument}/candles"
        params: dict[str, Any] = {}

        if price is not None:
            params["price"] = price
        if granularity is not None:
            params["granularity"] = granularity
        if count is not None:
            params["count"] = count
        if time_from is not None:
            params["from"] = time_from
        if time_to is not None:
            params["to"] = time_to
        if smooth is not None:
            params["smooth"] = str(smooth).lower()
        if include_first is not None:
            params["includeFirst"] = str(include_first).lower()
        if daily_alignment is not None:
            params["dailyAlignment"] = daily_alignment
        if alignment_timezone is not None:
            params["alignmentTimezone"] = alignment_timezone
        if weekly_alignment is not None:
            params["weeklyAlignment"] = weekly_alignment

        return self._client.request(
            "GET",
            path,
            params=params if params else None,
            accept_datetime_format=accept_datetime_format,
        )
