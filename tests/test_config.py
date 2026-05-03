from __future__ import annotations

from pathlib import Path

import pytest

from oanda_autotrader import config


def write_accounts_yaml(path: Path, *, environment: str = "FXPRACTICE") -> None:
    content = f"""
accounts:
  demo:
    environment: {environment}
    currency: CAD
    accounts:
      - name: Primary
        type: primary
        account_id: "101-000-0000000-001"
"""
    path.write_text(content.strip(), encoding="utf-8")


def test_load_account_groups_parses_yaml(tmp_path: Path) -> None:
    yaml_path = tmp_path / "accounts.yaml"
    write_accounts_yaml(yaml_path)
    groups = config.load_account_groups(str(yaml_path))
    assert "demo" in groups
    assert groups["demo"].environment == "practice"
    assert groups["demo"].accounts[0].name == "Primary"


def test_select_account_finds_entry(tmp_path: Path) -> None:
    yaml_path = tmp_path / "accounts.yaml"
    write_accounts_yaml(yaml_path)
    groups = config.load_account_groups(str(yaml_path))
    group, entry = config.select_account(groups, "demo", "Primary")
    assert entry.account_id == "101-000-0000000-001"
    assert group.currency == "CAD"


def test_resolve_account_credentials_reads_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    yaml_path = tmp_path / "accounts.yaml"
    write_accounts_yaml(yaml_path)
    monkeypatch.setenv("DEMO_OANDA_API_KEY", "token-demo")
    groups = config.load_account_groups(str(yaml_path))
    group, entry = config.select_account(groups, "demo", "Primary")
    resolved = config.resolve_account_credentials(group, entry)
    assert resolved.token == "token-demo"
    assert resolved.base_url == config.DEFAULT_PRACTICE_URL
    assert resolved.stream_base_url == config.DEFAULT_PRACTICE_STREAM_URL


def test_invalid_environment_raises(tmp_path: Path) -> None:
    yaml_path = tmp_path / "accounts.yaml"
    write_accounts_yaml(yaml_path, environment="BADENV")
    with pytest.raises(ValueError):
        config.load_account_groups(str(yaml_path))
