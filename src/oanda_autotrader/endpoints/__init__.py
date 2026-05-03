"""
Endpoint groupings live here to keep API surface area segmented by domain.
"""

from .accounts import AccountsAPI
from .accounts_async import AccountsAsyncAPI
from .instruments import InstrumentsAPI
from .instruments_async import InstrumentsAsyncAPI
from .orders import OrdersAPI

__all__ = [
    "AccountsAPI",
    "AccountsAsyncAPI",
    "InstrumentsAPI",
    "InstrumentsAsyncAPI",
    "OrdersAPI",
]
