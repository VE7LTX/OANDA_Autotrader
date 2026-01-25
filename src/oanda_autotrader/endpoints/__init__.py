"""
Endpoint groupings live here to keep API surface area segmented by domain.
"""

from .accounts import AccountsAPI
from .accounts_async import AccountsAsyncAPI

__all__ = ["AccountsAPI", "AccountsAsyncAPI"]
