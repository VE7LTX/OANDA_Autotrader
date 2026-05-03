from __future__ import annotations

import os

from oanda_autotrader.config import AccountEntry, AccountGroup, resolve_account_credentials


def test_resolve_account_credentials_accepts_legacy_env_names() -> None:
    os.environ["FXPRACTICE_APIKEY"] = "legacy-token"
    os.environ["FXPRACTICE_API_URL"] = "https://practice.example.com"
    os.environ["FXPRACTICE_STREAM_URL"] = "https://stream.practice.example.com"
    group = AccountGroup(
        key="demo",
        environment="practice",
        currency="CAD",
        accounts=[AccountEntry(name="Primary", type="primary", account_id="101-001-1")],
    )
    entry = group.accounts[0]
    resolved = resolve_account_credentials(group, entry)
    assert resolved.token == "legacy-token"
    assert resolved.base_url == "https://practice.example.com"
    assert resolved.stream_base_url == "https://stream.practice.example.com"
