# models/account.py – inline‑commented version
# Author: Ziggy (ChatGPT o3)
# Last Updated: 2025‑06‑19
"""Core dataclass models for the OANDA SDK.

This file defines three related structures:

1. **AccountSummary** – A lightweight view returned by `/v3/accounts` or
   `/v3/accounts/{id}/summary`.  Only high‑level metrics and no per‑trade detail.
2. **Account** – A full account payload (inherits `AccountSummary` and tacks on
   extra fields such as counts and hedging flag).
3. **Instrument** – Metadata for each tradeable symbol (pulled from
   `/v3/accounts/{id}/instruments`).

Inline comments explain why certain types are strings (`DecimalNumber`) and where
place‑holder `Any` lists will later be replaced by concrete `Order`, `Position`,
and `Trade` dataclasses.
"""

from __future__ import annotations  # allow forward‑refs in type hints

from dataclasses import dataclass, field
from typing import Any, List, Optional

# Local type aliases + base model
from .base import (
    OandaDataModel,  # common helper with .from_dict() / .to_dict()
    # primitive aliases (OANDA uses mostly strings for numeric precision)
    AccountID,
    DateTime,
    DecimalNumber,
    Integer,
    InstrumentName,
    Boolean,
    TransactionID,
)

# ---------------------------------------------------------------------------
# 1) AccountSummary – minimal snapshot of an account
# ---------------------------------------------------------------------------


@dataclass
class AccountSummary(OandaDataModel):
    """High‑level snapshot of an account’s state (balance, margin, P/L, …)."""

    # ------- identity -------
    id: AccountID                                      # primary key
    alias: Optional[str] = None                       # user‑friendly name
    currency: str = ""                                # account base currency

    # ------- balances -------
    balance: DecimalNumber = "0.0"                    # cash balance (string for precision)
    pl: DecimalNumber = "0.0"                         # realised profit / loss total
    unrealizedPL: DecimalNumber = "0.0"               # open trades P/L
    nav: DecimalNumber = "0.0"                        # Net Asset Value (balance + unrealised)

    # ------- timestamps and meta -------
    createdByUserID: Optional[Integer] = None          # who opened the account
    createdTime: Optional[DateTime] = None             # RFC3339 string
    guaranteedStopLossOrderMode: Optional[str] = None  # DISABLED | ALLOWED | REQUIRED

    # ------- resettable metrics (broker lets you zero these) -------
    resettablePL: DecimalNumber = "0.0"
    resettablePLTime: Optional[DateTime] = None

    # ------- fees (strings for precision) -------
    financing: DecimalNumber = "0.0"
    commission: DecimalNumber = "0.0"
    guaranteedExecutionFees: DecimalNumber = "0.0"

    # ------- placeholder collections (populated in full calls) -------
    # When Order/Position/Trade dataclasses exist, replace Any with those types.
    orders: List[Any] = field(default_factory=list)
    positions: List[Any] = field(default_factory=list)
    trades: List[Any] = field(default_factory=list)

    # ------- margin picture -------
    marginUsed: DecimalNumber = "0.0"                 # how much margin consumed
    marginAvailable: DecimalNumber = "0.0"            # free margin remaining
    positionValue: DecimalNumber = "0.0"              # value of all open positions

    # Margin‑closeout scenario metrics (worst‑case liquidation snapshot)
    marginCloseoutUnrealizedPL: DecimalNumber = "0.0"
    marginCloseoutNAV: DecimalNumber = "0.0"
    marginCloseoutMarginUsed: DecimalNumber = "0.0"
    marginCloseoutPercent: DecimalNumber = "0.0"
    marginCloseoutPositionValue: DecimalNumber = "0.0"

    # Withdraw & call thresholds
    withdrawalLimit: DecimalNumber = "0.0"
    marginCallMarginUsed: DecimalNumber = "0.0"
    marginCallPercent: DecimalNumber = "0.0"

    # The latest transaction id seen – handy for polling `/changes` endpoint
    lastTransactionID: Optional[TransactionID] = None


# ---------------------------------------------------------------------------
# 2) Account (full) – extends AccountSummary with additional fields
# ---------------------------------------------------------------------------


@dataclass
class Account(AccountSummary):
    """Full account payload from `/v3/accounts/{id}`."""

    # Whether the account can hold both long & short positions simultaneously
    hedgingEnabled: Optional[Boolean] = None

    # Timestamp of the most recent filled order (helps polling systems)
    lastOrderFillTimestamp: Optional[DateTime] = None

    # Quick counts so the UI can show *how many* objects to expect
    openTradeCount: Optional[Integer] = None
    openPositionCount: Optional[Integer] = None
    pendingOrderCount: Optional[Integer] = None

    # orders / positions / trades lists are inherited as empty lists; the
    # REST response populates them if `includeOrders=true` is requested.


# ---------------------------------------------------------------------------
# 3) Instrument – static metadata for each tradeable symbol
# ---------------------------------------------------------------------------


@dataclass
class Instrument(OandaDataModel):
    """Market definition (pip size, margin rate, display precision, …)."""

    # ------- identity -------
    name: InstrumentName                               # e.g. "EUR_USD"
    type: str                                          # CURRENCY | CFD | METAL | CRYPTO
    displayName: str                                   # prettified, e.g. "EUR/USD"

    # ------- price granularity -------
    pipLocation: Integer                               # exponent for 1 pip (‑4 → 0.0001)
    displayPrecision: Integer                          # #digits to show in UI
    tradeUnitsPrecision: Integer                       # smallest order unit exponent

    # ------- trading limits -------
    minimumTradeSize: DecimalNumber
    maximumTrailingStopDistance: DecimalNumber
    minimumTrailingStopDistance: DecimalNumber
    maximumPositionSize: DecimalNumber
    maximumOrderUnits: DecimalNumber
    marginRate: DecimalNumber                          # leverage = 1 / marginRate

    # ---------- miscellaneous -------
    guaranteedStopLossOrderModeForInstrument: Optional[str] = None
    tags: List[dict] = field(default_factory=list)      # free‑form descriptors
