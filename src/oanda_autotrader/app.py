"""
Runtime assembly helpers.

Purpose:
- Keep wiring logic (config -> client -> endpoints) in one place.
- Make it easy to trace how a YAML entry becomes an authenticated API call.

Logic flow:
1) load_account_client() reads accounts.yaml.
2) It finds a group + account entry by name.
3) resolve_account_credentials() expands that entry using env vars.
4) build_account_client() creates the HTTP client and endpoint group.
5) The caller invokes endpoint methods (list_accounts, etc.).
"""

from __future__ import annotations

from .config import (
    AppConfig,
    load_account_groups,
    resolve_account_credentials,
    select_account,
)
from .http import OandaHttpClient
from .async_http import OandaAsyncHttpClient
from .endpoints.accounts import AccountsAPI
from .endpoints.accounts_async import AccountsAsyncAPI
from .validation import validate_account_groups, validate_connectivity
from .streaming import OandaStreamClient


def build_account_client(config: AppConfig) -> AccountsAPI:
    """
    Create an AccountsAPI client for a resolved account configuration.
    """

    http_client = OandaHttpClient(
        base_url=config.base_url,
        token=config.token,
        timeout_seconds=config.settings.request_timeout_seconds,
        requests_per_second=config.settings.requests_per_second,
        debug_logging=config.settings.debug_logging,
    )
    return AccountsAPI(http_client)


def build_account_client_async(config: AppConfig) -> AccountsAsyncAPI:
    """
    Create an async AccountsAPI client for a resolved account configuration.
    """

    http_client = OandaAsyncHttpClient(
        base_url=config.base_url,
        token=config.token,
        timeout_seconds=config.settings.request_timeout_seconds,
        requests_per_second=config.settings.requests_per_second,
        debug_logging=config.settings.debug_logging,
    )
    return AccountsAsyncAPI(http_client)


def load_account_client(
    accounts_path: str, group_name: str, account_name: str
) -> AccountsAPI:
    """
    Find an account by group name + account name and return an AccountsAPI client.
    """

    groups = load_account_groups(accounts_path)
    warnings = validate_account_groups(groups)
    if warnings:
        # Fail fast so missing/duplicate values are fixed before HTTP calls.
        raise ValueError("accounts.yaml validation warnings: " + "; ".join(warnings))
    group, entry = select_account(groups, group_name, account_name)
    resolved = resolve_account_credentials(group, entry)
    return build_account_client(resolved)


def load_account_client_async(
    accounts_path: str, group_name: str, account_name: str
) -> AccountsAsyncAPI:
    """
    Find an account by group name + account name and return an async AccountsAPI client.
    """

    groups = load_account_groups(accounts_path)
    warnings = validate_account_groups(groups)
    if warnings:
        # Fail fast so missing/duplicate values are fixed before HTTP calls.
        raise ValueError("accounts.yaml validation warnings: " + "; ".join(warnings))
    group, entry = select_account(groups, group_name, account_name)
    resolved = resolve_account_credentials(group, entry)
    return build_account_client_async(resolved)


def validate_account_connection(
    accounts_path: str, group_name: str, account_name: str
) -> dict[str, object]:
    """
    Validate accounts.yaml + credentials by calling GET /v3/accounts.
    """

    groups = load_account_groups(accounts_path)
    warnings = validate_account_groups(groups)
    if warnings:
        # Treat validation warnings as hard errors for connection checks.
        raise ValueError("accounts.yaml validation warnings: " + "; ".join(warnings))

    group, entry = select_account(groups, group_name, account_name)
    resolved = resolve_account_credentials(group, entry)
    http_client = OandaHttpClient(base_url=resolved.base_url, token=resolved.token)
    return validate_connectivity(http_client)


def build_stream_client(config: AppConfig) -> OandaStreamClient:
    """
    Create a streaming client with reconnect/backoff settings.
    """

    return OandaStreamClient(
        stream_base_url=config.stream_base_url,
        token=config.token,
        timeout_seconds=config.settings.stream_timeout_seconds,
        reconnect=config.settings.reconnect,
        max_retries=config.settings.max_retries,
        backoff_base_seconds=config.settings.backoff_base_seconds,
        backoff_max_seconds=config.settings.backoff_max_seconds,
    )


def load_stream_client(
    accounts_path: str, group_name: str, account_name: str
) -> OandaStreamClient:
    """
    Find an account by group name + account name and return a stream client.
    """

    groups = load_account_groups(accounts_path)
    warnings = validate_account_groups(groups)
    if warnings:
        raise ValueError("accounts.yaml validation warnings: " + "; ".join(warnings))
    group, entry = select_account(groups, group_name, account_name)
    resolved = resolve_account_credentials(group, entry)
    return build_stream_client(resolved)
