"""
Validation helpers for accounts.yaml and API connectivity.

Purpose:
- Validate local config structure early, before making network calls.
- Provide a single place for connectivity checks with clear tracing.

Sources:
- accounts.yaml (structure/values).
- OANDA v20 API (GET /v3/accounts) for credential validation.

Logic flow:
1) validate_account_groups() inspects AccountGroup entries for common issues.
2) validate_connectivity() hits /v3/accounts to confirm token/base URL.
3) Callers can combine both in sequence to fail fast and trace problems.
"""

from __future__ import annotations

from typing import Any

import requests

from .config import AccountGroup
from .http import OandaHttpClient


def validate_account_groups(groups: dict[str, AccountGroup]) -> list[str]:
    """
    Validate accounts.yaml structure and return warnings.

    Inputs:
    - groups: output of load_account_groups().

    Outputs:
    - List of warning strings (empty list means no issues detected).

    Next:
    - Callers can treat warnings as errors or surface them to users.
    """

    warnings: list[str] = []

    for group_name, group in groups.items():
        # Currency should be a 3-letter code like CAD/USD/EUR.
        if len(group.currency) != 3 or not group.currency.isalpha():
            warnings.append(
                f"Group '{group_name}' currency '{group.currency}' should be a 3-letter code."
            )

        # Account names should be unique within a group for stable lookups.
        names = [entry.name for entry in group.accounts]
        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            warnings.append(
                f"Group '{group_name}' has duplicate account names: {sorted(duplicates)}."
            )

        # Account IDs should be strings with digits and dashes.
        for entry in group.accounts:
            if not entry.account_id or not isinstance(entry.account_id, str):
                warnings.append(
                    f"Group '{group_name}' account '{entry.name}' has empty account_id."
                )
                continue
            if not all(ch.isdigit() or ch == "-" for ch in entry.account_id):
                warnings.append(
                    f"Group '{group_name}' account '{entry.name}' has nonstandard account_id."
                )

    return warnings


def validate_connectivity(
    client: OandaHttpClient,
) -> dict[str, Any]:
    """
    Validate API connectivity using GET /v3/accounts.

    Inputs:
    - client: authenticated OandaHttpClient.

    Outputs:
    - Dict with ok/status/message/payload for easy logging and tracing.

    Next:
    - If ok is False, check message for auth or URL issues.
    """

    try:
        payload = client.request("GET", "/v3/accounts")
        return {"ok": True, "status": 200, "message": "OK", "payload": payload}
    except requests.HTTPError as exc:
        response = exc.response
        status = response.status_code if response is not None else None
        payload = None
        if response is not None:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text
        return {
            "ok": False,
            "status": status,
            "message": f"HTTP error: {exc}",
            "payload": payload,
        }
    except requests.RequestException as exc:
        return {"ok": False, "status": None, "message": f"Request error: {exc}", "payload": None}
