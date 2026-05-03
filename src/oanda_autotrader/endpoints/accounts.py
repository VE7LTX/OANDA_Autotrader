"""
Accounts endpoints (v20).

Source:
- OANDA v20 REST API docs (Accounts endpoints).

Included routes:
- GET /v3/accounts
- GET /v3/accounts/{accountID}
- GET /v3/accounts/{accountID}/summary

Logic flow (per method):
1) Build path with account ID if needed.
2) Pass path + headers to OandaHttpClient.
3) Return raw JSON for easy tracing and quick iteration.

Tracing notes:
- If the token is invalid or missing, errors surface in http.py.
- If account IDs are wrong, the API will return 4xx responses.
"""

from __future__ import annotations

from typing import Any

from ..http import OandaHttpClient


class AccountsAPI:
    """
    Endpoint grouping for account-related routes.
    """

    def __init__(self, client: OandaHttpClient) -> None:
        self._client = client

    def list_accounts(self) -> dict[str, Any]:
        """
        GET /v3/accounts

        Inputs: none (token is provided by the client).
        Outputs: JSON payload containing authorized accounts.
        Next: Use account IDs from the response for detail/summary calls.
        """

        return self._client.request("GET", "/v3/accounts")

    def get_account(
        self, account_id: str, *, accept_datetime_format: str | None = None
    ) -> dict[str, Any]:
        """
        GET /v3/accounts/{accountID}

        Inputs:
        - account_id: ID from list_accounts() or your config.
        - accept_datetime_format: optional OANDA datetime format header.

        Outputs:
        - Full account details (including orders/trades/positions).
        """

        path = f"/v3/accounts/{account_id}"
        return self._client.request(
            "GET", path, accept_datetime_format=accept_datetime_format
        )

    def get_account_summary(
        self, account_id: str, *, accept_datetime_format: str | None = None
    ) -> dict[str, Any]:
        """
        GET /v3/accounts/{accountID}/summary

        Inputs:
        - account_id: ID from list_accounts() or your config.
        - accept_datetime_format: optional OANDA datetime format header.

        Outputs:
        - Summary data for the account (balances, NAV, etc.).
        """

        path = f"/v3/accounts/{account_id}/summary"
        return self._client.request(
            "GET", path, accept_datetime_format=accept_datetime_format
        )

    def get_instruments(
        self, account_id: str, *, instruments: list[str] | None = None
    ) -> dict[str, Any]:
        """
        GET /v3/accounts/{accountID}/instruments

        Inputs:
        - account_id: ID from list_accounts() or your config.
        - instruments: optional list of instrument names to filter.

        Outputs:
        - List of tradeable instruments for the account.
        """

        path = f"/v3/accounts/{account_id}/instruments"
        params = {"instruments": ",".join(instruments)} if instruments else None
        return self._client.request("GET", path, params=params)
