"""
Async Accounts endpoints (v20).

Source:
- OANDA v20 REST API docs (Accounts endpoints).

Included routes:
- GET /v3/accounts
- GET /v3/accounts/{accountID}
- GET /v3/accounts/{accountID}/summary

Logic flow (per method):
1) Build path with account ID if needed.
2) Pass path + headers to OandaAsyncHttpClient.
3) Return raw JSON for easy tracing and quick iteration.
"""

from __future__ import annotations

from typing import Any

from ..async_http import OandaAsyncHttpClient


class AccountsAsyncAPI:
    """
    Async endpoint grouping for account-related routes.
    """

    def __init__(self, client: OandaAsyncHttpClient) -> None:
        self._client = client

    async def list_accounts(self) -> dict[str, Any]:
        """
        GET /v3/accounts
        """

        return await self._client.request("GET", "/v3/accounts")

    async def get_account(
        self, account_id: str, *, accept_datetime_format: str | None = None
    ) -> dict[str, Any]:
        """
        GET /v3/accounts/{accountID}
        """

        path = f"/v3/accounts/{account_id}"
        return await self._client.request(
            "GET", path, accept_datetime_format=accept_datetime_format
        )

    async def get_account_summary(
        self, account_id: str, *, accept_datetime_format: str | None = None
    ) -> dict[str, Any]:
        """
        GET /v3/accounts/{accountID}/summary
        """

        path = f"/v3/accounts/{account_id}/summary"
        return await self._client.request(
            "GET", path, accept_datetime_format=accept_datetime_format
        )

    async def get_instruments(
        self, account_id: str, *, instruments: list[str] | None = None
    ) -> dict[str, Any]:
        """
        GET /v3/accounts/{accountID}/instruments
        """

        path = f"/v3/accounts/{account_id}/instruments"
        params = {"instruments": ",".join(instruments)} if instruments else None
        return await self._client.request("GET", path, params=params)
