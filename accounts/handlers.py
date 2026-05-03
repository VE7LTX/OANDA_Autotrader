# accounts/handlers.py
# Author: Ziggy (ChatGPT o3) for Matt Schafer (VE7LTX)
# Created: 2025-06-19
# Last Updated: 2025-06-19
"""
AccountHandler – wrapper around OANDA v20 *Account* endpoints.

This version uses **absolute imports** (Option A) because `accounts` is a top-level
package in your current directory layout.  If you later nest everything under an
`oanda_sdk/` package you’ll revert to relative imports (or update the namespace
accordingly).

Public surface (v1):
    • get_accounts()
    • get_account_details()
    • get_account_summary()
    • get_instruments()  – convenience passthrough (mirrors InstrumentHandler)
    • configure_account()

All methods are decorated with ``retry`` + ``track_latency`` and return the
strongly-typed dataclasses declared in ``models.account``.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from client import api_client  # absolute import – repo-root modules
from config import settings
from models.account import (
    Account,
    AccountSummary,
    Instrument,
    AccountID,
    InstrumentName,
)
from utils.decorators import retry, track_latency
from utils.exceptions import OandaApiError, ParseError, OandaError

logger = logging.getLogger(__name__)


class AccountHandler:
    """High-level helper for OANDA account endpoints."""

    def __init__(self, client=api_client):
        if client is None:
            raise OandaError("ApiClient not available – configuration failed to load.")
        self.client = client
        self.default_account_id: str = settings.account_id

    # ------------------------------------------------------------------
    # GET /v3/accounts
    # ------------------------------------------------------------------

    @retry()
    @track_latency
    def get_accounts(self) -> List[AccountSummary]:
        endpoint = "/v3/accounts"
        logger.info("Fetching account list …")
        data = self.client.get(endpoint)
        if "accounts" not in data or not isinstance(data["accounts"], list):
            raise ParseError(f"Unexpected payload for {endpoint}: missing 'accounts'.")
        return [AccountSummary.from_dict(a) for a in data["accounts"]]

    # ------------------------------------------------------------------
    # GET /v3/accounts/{id}
    # ------------------------------------------------------------------

    @retry()
    @track_latency
    def get_account_details(self, account_id: Optional[AccountID] = None) -> Account:
        acc_id = account_id or self.default_account_id
        if not acc_id:
            raise ValueError("Account ID must be provided or set in .env.")
        endpoint = f"/v3/accounts/{acc_id}"
        logger.info("Fetching full details for %s", acc_id[:8] + "…")
        data = self.client.get(endpoint)
        if "account" not in data:
            raise ParseError(f"Unexpected payload for {endpoint}: missing 'account'.")
        return Account.from_dict(data["account"])

    # ------------------------------------------------------------------
    # GET /v3/accounts/{id}/summary
    # ------------------------------------------------------------------

    @retry()
    @track_latency
    def get_account_summary(self, account_id: Optional[AccountID] = None) -> AccountSummary:
        acc_id = account_id or self.default_account_id
        endpoint = f"/v3/accounts/{acc_id}/summary"
        logger.info("Fetching summary for %s", acc_id[:8] + "…")
        data = self.client.get(endpoint)
        key = "accountSummary" if "accountSummary" in data else "account"
        if key not in data:
            raise ParseError(f"Unexpected payload for {endpoint}: missing '{key}'.")
        summary = AccountSummary.from_dict(data[key])
        if "lastTransactionID" in data:
            summary.lastTransactionID = data["lastTransactionID"]
        return summary

    # ------------------------------------------------------------------
    # GET /v3/accounts/{id}/instruments – thin wrapper; prefer InstrumentHandler
    # ------------------------------------------------------------------

    @retry()
    @track_latency
    def get_instruments(
        self,
        account_id: Optional[AccountID] = None,
        *,
        instruments: Optional[List[InstrumentName]] = None,
    ) -> List[Instrument]:
        acc_id = account_id or self.default_account_id
        endpoint = f"/v3/accounts/{acc_id}/instruments"
        params = {"instruments": ",".join(instruments)} if instruments else None
        logger.info("Fetching instruments via AccountHandler (id=%s) …", acc_id[:8] + "…")
        data = self.client.get(endpoint, params=params)
        if "instruments" not in data or not isinstance(data["instruments"], list):
            raise ParseError(f"Unexpected payload for {endpoint}: missing 'instruments'.")
        return [Instrument.from_dict(d) for d in data["instruments"]]

    # ------------------------------------------------------------------
    # PATCH /v3/accounts/{id}/configuration
    # ------------------------------------------------------------------

    @retry()
    @track_latency
    def configure_account(self, cfg: dict, *, account_id: Optional[AccountID] = None) -> dict:
        if not cfg:
            raise ValueError("Configuration dict must not be empty.")
        acc_id = account_id or self.default_account_id
        endpoint = f"/v3/accounts/{acc_id}/configuration"
        logger.info("Patching account %s with %s", acc_id[:8] + "…", cfg)
        return self.client.patch(endpoint, data=cfg)


# Convenience singleton (mirrors style used elsewhere)
try:
    account_handler: AccountHandler | None = AccountHandler(api_client)
except OandaError as exc:
    account_handler = None
    logger.error("AccountHandler could not be instantiated: %s", exc)
