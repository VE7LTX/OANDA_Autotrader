"""
Streaming client for OANDA v20 price/transaction streams.

Notes:
- OANDA uses HTTP streaming (chunked) for live updates, not WebSocket.
- This module focuses on async streaming over HTTP for low latency updates.

Sources:
- stream_base_url from config.py (defaults to stream-fxpractice/fxtrade).

Logic flow:
1) Build stream URL for pricing or transactions.
2) Open a long-lived HTTP request with auth headers.
3) Yield decoded JSON messages line-by-line.
4) On disconnect, apply backoff and reconnect (optional).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable
import json
import asyncio
import random

import aiohttp

from .models import parse_stream_message, StreamMessage


@dataclass
class OandaStreamClient:
    """
    Async streaming client (pricing + transactions).
    """

    stream_base_url: str
    token: str
    timeout_seconds: int = 0  # 0 disables total timeout for long-lived streams.
    reconnect: bool = True
    max_retries: int | None = None
    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 15.0
    _session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "OandaStreamClient":
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds or None)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _stream(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        parser: Callable[[dict[str, Any]], StreamMessage] | None = None,
    ) -> AsyncIterator[StreamMessage]:
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds or None)
            self._session = aiohttp.ClientSession(timeout=timeout)

        url = f"{self.stream_base_url.rstrip('/')}{path}"
        headers = {"Authorization": f"Bearer {self.token}"}
        attempt = 0

        while True:
            try:
                async with self._session.get(url, params=params, headers=headers) as response:
                    response.raise_for_status()
                    async for raw_line in response.content:
                        line = raw_line.decode("utf-8").strip()
                        if not line:
                            continue
                        try:
                            payload = json.loads(line)
                        except json.JSONDecodeError:
                            # Skip malformed lines to keep stream alive.
                            continue
                        yield parser(payload) if parser else parse_stream_message(payload)
                # A clean stream end should not auto-reconnect unless enabled.
                if not self.reconnect:
                    break
            except (aiohttp.ClientError, asyncio.TimeoutError):
                if not self.reconnect:
                    raise
            attempt += 1
            if self.max_retries is not None and attempt > self.max_retries:
                break
            # Exponential backoff with jitter.
            delay = min(self.backoff_base_seconds * (2 ** (attempt - 1)), self.backoff_max_seconds)
            delay += random.uniform(0, 0.25 * delay)
            await asyncio.sleep(delay)

    async def stream_pricing(
        self, account_id: str, instruments: list[str]
    ) -> AsyncIterator[StreamMessage]:
        """
        Stream pricing updates for a list of instruments.
        """

        params = {"instruments": ",".join(instruments)}
        path = f"/v3/accounts/{account_id}/pricing/stream"
        async for message in self._stream(path, params=params):
            yield message

    async def stream_transactions(self, account_id: str) -> AsyncIterator[StreamMessage]:
        """
        Stream transactions for the given account.
        """

        path = f"/v3/accounts/{account_id}/transactions/stream"
        async for message in self._stream(path):
            yield message
