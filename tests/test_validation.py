from __future__ import annotations

import pytest

from oanda_autotrader.config import AccountEntry, AccountGroup
from oanda_autotrader.validation import validate_account_groups


def test_validate_account_groups_detects_duplicates() -> None:
    group = AccountGroup(
        key="demo",
        environment="practice",
        currency="CAD",
        accounts=[
            AccountEntry(name="Primary", type="primary", account_id="101-000-0000000-001"),
            AccountEntry(name="Primary", type="primary", account_id="101-000-0000000-002"),
        ],
    )
    warnings = validate_account_groups({"demo": group})
    assert any("duplicate account names" in warning for warning in warnings)


def test_validate_account_groups_invalid_currency() -> None:
    group = AccountGroup(
        key="demo",
        environment="practice",
        currency="CA",
        accounts=[AccountEntry(name="Primary", type="primary", account_id="101-000-0000000-001")],
    )
    warnings = validate_account_groups({"demo": group})
    assert any("currency" in warning for warning in warnings)


def test_validate_account_groups_account_id_format() -> None:
    group = AccountGroup(
        key="demo",
        environment="practice",
        currency="CAD",
        accounts=[AccountEntry(name="Primary", type="primary", account_id="ABC123")],
    )
    warnings = validate_account_groups({"demo": group})
    assert any("nonstandard account_id" in warning for warning in warnings)
