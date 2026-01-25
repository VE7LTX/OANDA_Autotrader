"""
Configuration loader and credential resolver.

Purpose:
- Centralize how account metadata and credentials are assembled.
- Keep tracing simple: YAML -> dataclasses -> resolved config -> HTTP client.

Sources:
- accounts.yaml (local file, gitignored): account group metadata and IDs.
- environment variables (.env is recommended, gitignored): secrets and overrides.

Logic flow (high level):
1) load_account_groups() reads accounts.yaml and builds AccountGroup entries.
2) select_account() picks a group + account entry by name.
3) resolve_account_credentials() converts that selection into AppConfig by:
   - mapping "FXPRACTICE"/"FXTRADE" to "practice"/"live"
   - selecting default env var names per environment
   - pulling tokens/base URLs from environment variables
4) AppConfig is consumed by app.py -> http.py -> endpoints/*.

Tracing notes:
- If a value is missing, errors are raised where it is first required so the
  caller knows which source (YAML vs env) is incomplete.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import os

import yaml

DEFAULT_PRACTICE_URL = "https://api-fxpractice.oanda.com"
DEFAULT_LIVE_URL = "https://api-fxtrade.oanda.com"
DEFAULT_PRACTICE_STREAM_URL = "https://stream-fxpractice.oanda.com"
DEFAULT_LIVE_STREAM_URL = "https://stream-fxtrade.oanda.com"
_ENV_LOADED = False


@dataclass(frozen=True)
class AccountEntry:
    """
    One account entry inside a group.

    Fields map 1:1 to YAML keys for easy tracing.
    """

    name: str
    type: str
    account_id: str


@dataclass(frozen=True)
class AccountGroup:
    """
    Group of accounts (ex: demo or live).
    """

    key: str
    environment: str
    currency: str
    accounts: list[AccountEntry]


@dataclass(frozen=True)
class AppSettings:
    """
    Runtime tuning knobs for reliability and performance.
    """

    request_timeout_seconds: int
    stream_timeout_seconds: int
    reconnect: bool
    max_retries: int | None
    backoff_base_seconds: float
    backoff_max_seconds: float
    requests_per_second: int
    debug_logging: bool


@dataclass(frozen=True)
class AppConfig:
    """
    Resolved runtime config for a specific account.

    This is derived from AccountGroup + AccountEntry + environment variables.
    """

    group_name: str
    environment: str
    currency: str
    account_name: str
    account_type: str
    account_id: str
    token: str
    base_url: str
    stream_base_url: str
    settings: AppSettings


def _normalize_environment(value: str) -> str:
    env = value.strip().lower()
    if env in {"practice", "fxpractice", "fx_practice", "sandbox"}:
        return "practice"
    if env in {"live", "fxtrade", "fx_trade", "production", "prod"}:
        return "live"
    raise ValueError(f"Unsupported environment '{value}'. Use 'practice' or 'live'.")


def _default_token_env(environment: str) -> str:
    # Tokens are separated for demo (practice) vs live.
    return "DEMO_OANDA_API_KEY" if environment == "practice" else "LIVE_OANDA_API_KEY"


def _default_base_url(environment: str) -> str:
    # Base URLs default to OANDA's official fxPractice/fxTrade endpoints.
    return DEFAULT_PRACTICE_URL if environment == "practice" else DEFAULT_LIVE_URL


def _default_stream_base_url(environment: str) -> str:
    # Streaming URLs default to OANDA's official stream endpoints.
    return (
        DEFAULT_PRACTICE_STREAM_URL
        if environment == "practice"
        else DEFAULT_LIVE_STREAM_URL
    )


def _read_env(var_name: str, *, required: bool) -> str | None:
    # Single place to enforce "required" vs "optional" env behavior.
    value = os.getenv(var_name)
    if required and not value:
        raise ValueError(f"Missing required environment variable '{var_name}'.")
    return value


def _read_int(var_name: str, default: int) -> int:
    value = os.getenv(var_name)
    if value is None or value == "":
        return default
    return int(value)


def _read_float(var_name: str, default: float) -> float:
    value = os.getenv(var_name)
    if value is None or value == "":
        return default
    return float(value)


def _read_bool(var_name: str, default: bool) -> bool:
    value = os.getenv(var_name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _read_optional_int(var_name: str) -> int | None:
    value = os.getenv(var_name)
    if value is None or value == "":
        return None
    return int(value)


def _load_env_file(path: str = ".env") -> None:
    # Minimal .env loader to avoid external dependencies.
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    if not os.path.exists(path):
        _ENV_LOADED = True
        return

    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and value and key not in os.environ:
                os.environ[key] = value

    _ENV_LOADED = True


def _parse_groups(raw: Any) -> dict[str, AccountGroup]:
    if not isinstance(raw, dict) or "accounts" not in raw:
        raise ValueError("accounts.yaml must contain a top-level 'accounts' mapping.")

    groups = raw["accounts"]
    if not isinstance(groups, dict):
        raise ValueError("'accounts' must be a mapping of group names to definitions.")

    parsed: dict[str, AccountGroup] = {}
    for key, group in groups.items():
        if not isinstance(group, dict):
            raise ValueError(f"Group '{key}' must be a mapping.")

        try:
            # Environment drives token and base URL selection.
            environment = _normalize_environment(str(group["environment"]))
            currency = str(group["currency"])
            account_entries = group["accounts"]
        except KeyError as exc:
            raise ValueError(f"Group '{key}' missing required key: {exc}") from exc

        if not isinstance(account_entries, list):
            raise ValueError(f"Group '{key}' accounts must be a list.")

        accounts: list[AccountEntry] = []
        for idx, entry in enumerate(account_entries):
            if not isinstance(entry, dict):
                raise ValueError(f"Account entry {idx} in group '{key}' must be a mapping.")
            try:
                name = str(entry["name"])
                account_type = str(entry["type"])
                account_id = str(entry["account_id"])
            except KeyError as exc:
                raise ValueError(
                    f"Account entry {idx} in group '{key}' missing key: {exc}"
                ) from exc
            # Store raw IDs as strings so we never lose formatting.
            accounts.append(AccountEntry(name=name, type=account_type, account_id=account_id))

        parsed[key] = AccountGroup(
            key=str(key),
            environment=environment,
            currency=currency,
            accounts=accounts,
        )

    return parsed


def load_account_groups(path: str) -> dict[str, AccountGroup]:
    """
    Load account groups from accounts.yaml.

    Inputs:
    - path: path to accounts.yaml (typically project root).

    Outputs:
    - Dict mapping group name -> AccountGroup.

    Next:
    - select_account() chooses the specific account for use.
    """

    # YAML is intentionally kept small and human-readable.
    with open(path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return _parse_groups(raw)


def select_account(
    groups: dict[str, AccountGroup], group_name: str, account_name: str
) -> tuple[AccountGroup, AccountEntry]:
    """
    Find a specific account by group name + account name.

    Inputs:
    - groups: output of load_account_groups().
    - group_name: top-level key (ex: demo, live).
    - account_name: entry name inside that group (ex: Primary).

    Outputs:
    - (AccountGroup, AccountEntry) pair for downstream resolution.
    """

    group = groups.get(group_name)
    if not group:
        available = ", ".join(sorted(groups.keys()))
        raise ValueError(f"Group '{group_name}' not found. Available: {available}")

    matches = [entry for entry in group.accounts if entry.name == account_name]
    if not matches:
        available = ", ".join(entry.name for entry in group.accounts)
        raise ValueError(
            f"Account '{account_name}' not found in group '{group_name}'. "
            f"Available: {available}"
        )
    if len(matches) > 1:
        raise ValueError(
            f"Account name '{account_name}' is not unique in group '{group_name}'."
        )
    return group, matches[0]


def resolve_account_credentials(
    group: AccountGroup, entry: AccountEntry
) -> AppConfig:
    """
    Resolve a (group, entry) pair into concrete credentials.

    Inputs:
    - group: AccountGroup from accounts.yaml.
    - entry: AccountEntry from accounts.yaml.

    Outputs:
    - AppConfig with token + base_url ready for HTTP usage.

    Next:
    - Feed AppConfig into OandaHttpClient or app.py helper functions.
    """

    # Load local .env file once so OANDA_API_KEY is available without manual export.
    _load_env_file()

    # Tokens are stored in env vars, keyed by environment.
    # Token selection is based on group environment (practice/live).
    token_env = _default_token_env(group.environment)
    token = _read_env(token_env, required=True)

    # Base URL override is optional; defaults to official endpoints.
    base_url = _read_env(
        "OANDA_API_BASE_PRACTICE" if group.environment == "practice" else "OANDA_API_BASE_LIVE",
        required=False,
    )
    if not base_url:
        base_url = _default_base_url(group.environment)

    # Stream base URL override is optional; defaults to official stream endpoints.
    stream_base_url = _read_env(
        "OANDA_STREAM_BASE_PRACTICE"
        if group.environment == "practice"
        else "OANDA_STREAM_BASE_LIVE",
        required=False,
    )
    if not stream_base_url:
        stream_base_url = _default_stream_base_url(group.environment)

    settings = AppSettings(
        request_timeout_seconds=_read_int("OANDA_REQUEST_TIMEOUT_SECONDS", 30),
        stream_timeout_seconds=_read_int("OANDA_STREAM_TIMEOUT_SECONDS", 0),
        reconnect=_read_bool("OANDA_STREAM_RECONNECT", True),
        max_retries=_read_optional_int("OANDA_STREAM_MAX_RETRIES"),
        backoff_base_seconds=_read_float("OANDA_STREAM_BACKOFF_BASE_SECONDS", 0.5),
        backoff_max_seconds=_read_float("OANDA_STREAM_BACKOFF_MAX_SECONDS", 15.0),
        requests_per_second=_read_int("OANDA_REQUESTS_PER_SECOND", 100),
        debug_logging=_read_bool("OANDA_DEBUG_LOGGING", False),
    )

    return AppConfig(
        group_name=group.key,
        environment=group.environment,
        currency=group.currency,
        account_name=entry.name,
        account_type=entry.type,
        account_id=entry.account_id,
        token=token,
        base_url=base_url,
        stream_base_url=stream_base_url,
        settings=settings,
    )
