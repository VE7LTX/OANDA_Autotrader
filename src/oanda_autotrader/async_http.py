"""
Async HTTP client wrapper for OANDA v20 endpoints.

Purpose:
- Provide async I/O for higher throughput and concurrency.
- Keep endpoint modules focused on URL paths and parameters.

Sources:
- base_url: resolved in config.py (defaults to fxTrade/fxPractice URLs).
- token: resolved in config.py from environment variables.

Logic flow:
1) The caller instantiates OandaAsyncHttpClient with base_url + token.
2) Endpoint methods call request(method, path, ...).
3) request() builds the full URL, injects headers, and delegates to aiohttp.
4) JSON response is returned to the caller for downstream processing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import logging

import aiohttp

from .rate_limit import AsyncRateLimiter

logger = logging.getLogger(__name__)

@dataclass
class OandaAsyncHttpClient:
    """
    Minimal async HTTP client that handles auth + base URL.
    """

    base_url: str
    token: str
    timeout_seconds: int = 30
    requests_per_second: int | None = None
    debug_logging: bool = False
    _session: aiohttp.ClientSession | None = None
    _rate_limiter: AsyncRateLimiter | None = None

    async def __aenter__(self) -> "OandaAsyncHttpClient":
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            self._session = aiohttp.ClientSession(timeout=timeout)
        if self._rate_limiter is None and self.requests_per_second is not None:
            self._rate_limiter = AsyncRateLimiter(self.requests_per_second)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        accept_datetime_format: str | None = None,
    ) -> dict[str, Any]:
        """
        Send a single HTTP request and return JSON payload.

        Inputs:
        - method: HTTP method (GET, POST, etc.).
        - path: endpoint path (e.g., /v3/accounts).
        - params/json_body: query/body payloads as needed.
        - accept_datetime_format: optional header forwarded to OANDA.

        Outputs:
        - Parsed JSON response as a dict.
        """

        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            self._session = aiohttp.ClientSession(timeout=timeout)
        if self._rate_limiter is None and self.requests_per_second is not None:
            self._rate_limiter = AsyncRateLimiter(self.requests_per_second)

        url = f"{self.base_url.rstrip('/')}{path}"
        headers = {
            "Authorization": f"Bearer {self.token}",
        }
        if accept_datetime_format:
            headers["Accept-Datetime-Format"] = accept_datetime_format

        if self._rate_limiter:
            await self._rate_limiter.wait()
        if self.debug_logging:
            logger.info("HTTP %s %s", method.upper(), url)
        async with self._session.request(
            method=method.upper(),
            url=url,
            params=params,
            json=json_body,
            headers=headers,
        ) as response:
            response.raise_for_status()
            return await response.json()
