# client.py – absolute-import version for flat repo layout
# Author: Ziggy (ChatGPT o3) for Matt Schafer (VE7LTX)
# Created: 2025-06-19
# Last Updated: 2025-06-19
"""
Central HTTP wrapper for OANDA v20 REST.  Uses **absolute imports** because the
project is not wrapped in a parent package right now.

If you later move all modules under an `oanda_sdk/` package you’ll revert the
imports to `from oanda_sdk.config import settings`, etc.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import requests

# absolute-imports -----------------------------------------------------------
from config import settings  # global settings singleton (raises on failure)
from utils.exceptions import OandaApiError, RateLimitError, RequestError, ParseError

logger = logging.getLogger(__name__)

# Ensure settings loaded -----------------------------------------------------
if settings is None:
    raise ImportError("Configuration (settings) could not be loaded. Cannot initialize ApiClient.")


class ApiClient:
    """Core client for OANDA v20 REST calls."""

    def __init__(self):
        self.api_url: str = settings.api_url
        self.account_id: str = settings.account_id  # default account
        self._session: requests.Session = requests.Session()
        self._session.headers.update(settings.get_auth_headers())
        self._session.headers.update(settings.get_accept_datetime_format_headers())
        logger.info("ApiClient initialised for %s (%s)", settings.environment, self.api_url)

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    def _make_request(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
    ) -> Any:
        full_url = f"{self.api_url}{endpoint}"
        req_headers = self._session.headers.copy()
        if headers:
            req_headers.update(headers)

        payload = None
        if method.upper() in {"POST", "PUT", "PATCH"} and data is not None:
            req_headers.update(settings.get_content_headers())
            payload = json.dumps(data)

        logger.debug("REQUEST %s %s (params=%s)", method, full_url, params)

        try:
            resp = self._session.request(
                method=method.upper(),
                url=full_url,
                params=params,
                data=payload,
                headers=req_headers,
                timeout=10,
                stream=stream,
            )
        except requests.exceptions.RequestException as exc:
            logger.exception("HTTP request failed: %s", exc)
            raise RequestError(f"Request failed for {method} {full_url}: {exc}") from exc

        logger.debug("RESPONSE %s %s", resp.status_code, resp.reason)

        # Error handling --------------------------------------------------
        if not resp.ok:
            try:
                err_json = resp.json()
            except json.JSONDecodeError:
                err_json = {"errorMessage": resp.text[:500]}
            if resp.status_code == 429:
                raise RateLimitError(resp.status_code, err_json)
            raise OandaApiError(resp.status_code, err_json)

        # 204 No-Content
        if resp.status_code == 204:
            return None

        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            logger.error("Failed to decode JSON response: %s", exc)
            raise ParseError(f"Could not parse JSON: {exc}") from exc

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------

    def get(self, endpoint: str, *, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Any:
        return self._make_request("GET", endpoint, params=params, headers=headers)

    def post(self, endpoint: str, *, data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Any:
        return self._make_request("POST", endpoint, data=data, params=params, headers=headers)

    def put(self, endpoint: str, *, data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Any:
        return self._make_request("PUT", endpoint, data=data, params=params, headers=headers)

    def patch(self, endpoint: str, *, data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Any:
        return self._make_request("PATCH", endpoint, data=data, params=params, headers=headers)

    def delete(self, endpoint: str, *, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Any:
        return self._make_request("DELETE", endpoint, params=params, headers=headers)


# Singleton instance ---------------------------------------------------------
api_client: ApiClient | None
try:
    api_client = ApiClient()
except Exception as exc:  # broad catch so import never half-initialises
    logger.critical("ApiClient failed to initialise: %s", exc)
    api_client = None
