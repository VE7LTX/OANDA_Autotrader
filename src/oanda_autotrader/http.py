"""
HTTP client wrapper for OANDA v20 endpoints.

Purpose:
- Provide a single place to manage auth headers and base URL handling.
- Keep endpoint modules focused on URL paths and parameters.

Sources:
- base_url: resolved in config.py (defaults to fxTrade/fxPractice URLs).
- token: resolved in config.py from environment variables.

Logic flow:
1) The caller instantiates OandaHttpClient with base_url + token.
2) Endpoint methods call request(method, path, ...).
3) request() builds the full URL, injects headers, and delegates to requests.
4) JSON response is returned to the caller for downstream processing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import logging

import requests


@dataclass
class OandaHttpClient:
    """
    Minimal HTTP client that handles auth + base URL.
    """

    base_url: str
    token: str
    timeout_seconds: int = 30
    requests_per_second: int | None = None
    debug_logging: bool = False

    def __post_init__(self) -> None:
        self._session = requests.Session()
        self._rate_limiter = (
            RateLimiter(self.requests_per_second)
            if self.requests_per_second is not None
            else None
        )

    def request(
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

        Next:
        - Callers should validate response fields or map to models.
        """

        url = f"{self.base_url.rstrip('/')}{path}"
        headers = {
            "Authorization": f"Bearer {self.token}",
        }
        if accept_datetime_format:
            headers["Accept-Datetime-Format"] = accept_datetime_format

        if self._rate_limiter:
            self._rate_limiter.wait()
        if self.debug_logging:
            logger.info("HTTP %s %s", method.upper(), url)
        response = self._session.request(
            method=method.upper(),
            url=url,
            params=params,
            json=json_body,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
from .rate_limit import RateLimiter

logger = logging.getLogger(__name__)
