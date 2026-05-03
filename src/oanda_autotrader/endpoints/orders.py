"""
Order endpoints for practice execution experiments.
"""

from __future__ import annotations

from typing import Any

from ..http import OandaHttpClient


class OrdersAPI:
    def __init__(self, client: OandaHttpClient) -> None:
        self._client = client

    def create_order(self, account_id: str, order: dict[str, Any]) -> dict[str, Any]:
        path = f"/v3/accounts/{account_id}/orders"
        return self._client.request("POST", path, json_body={"order": order})

