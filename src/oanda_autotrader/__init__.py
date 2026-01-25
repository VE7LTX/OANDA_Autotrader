"""
OANDA Autotrader package scaffold.

This package is intentionally small and segmented so each module can evolve
without creating a tangled dependency graph. Import paths are exported here
to keep the public surface area obvious while the implementation remains
editable in smaller files.
"""

from .config import (
    AccountEntry,
    AccountGroup,
    AppConfig,
    AppSettings,
    load_account_groups,
    resolve_account_credentials,
    select_account,
)
from .http import OandaHttpClient
from .async_http import OandaAsyncHttpClient
from .endpoints.accounts import AccountsAPI
from .endpoints.accounts_async import AccountsAsyncAPI
from .streaming import OandaStreamClient
from .models import (
    StreamMessage,
    PriceMessage,
    TransactionMessage,
    HeartbeatMessage,
    parse_stream_message,
)
from .validation import validate_account_groups, validate_connectivity
from .app import (
    validate_account_connection,
    build_account_client_async,
    load_account_client_async,
    build_stream_client,
    load_stream_client,
)
from .metrics import LatencyTracker, LatencySample, LatencyStats
from .monitor import measure_account_latency, sample_practice_live_latency

__all__ = [
    "AccountEntry",
    "AccountGroup",
    "AppConfig",
    "AppSettings",
    "load_account_groups",
    "resolve_account_credentials",
    "select_account",
    "OandaHttpClient",
    "OandaAsyncHttpClient",
    "AccountsAPI",
    "AccountsAsyncAPI",
    "OandaStreamClient",
    "StreamMessage",
    "PriceMessage",
    "TransactionMessage",
    "HeartbeatMessage",
    "parse_stream_message",
    "validate_account_groups",
    "validate_connectivity",
    "validate_account_connection",
    "build_account_client_async",
    "load_account_client_async",
    "build_stream_client",
    "load_stream_client",
    "LatencyTracker",
    "LatencySample",
    "LatencyStats",
    "measure_account_latency",
    "sample_practice_live_latency",
]
