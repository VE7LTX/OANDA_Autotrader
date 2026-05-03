# instruments/handlers.py
# Author: Ziggy (OpenAI o3)
# Last update: 2025-06-19
"""
InstrumentHandler
=================
Thin wrapper around the two OANDA endpoints that expose instrument metadata:

1.  GET /v3/accounts/{accountID}/instruments
    • returns the list of *trade-able* instruments for a given account.
2.  GET /v3/instruments/{instrument}
    • returns the granular metadata for one instrument by name.

The class caches the full instrument universe for 15 minutes so repeated CLI
calls don’t hit the API rate limit.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Absolute-path imports – work in a flat repo tree (no leading dots)
# ---------------------------------------------------------------------------
from client import api_client                      # shared requests wrapper
from config import settings                        # holds .env settings
from models.account import Instrument, AccountID, InstrumentName
from utils.decorators import retry, track_latency  # resilience helpers
from utils.exceptions import OandaApiError, ParseError, OandaError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Small helper object for caching with expiry
# ---------------------------------------------------------------------------
class _CacheEntry:
    """Stores a payload + absolute expiry timestamp."""

    __slots__ = ("payload", "expires_at")

    def __init__(self, payload: List[Instrument], ttl: int):
        self.payload: List[Instrument] = payload
        self.expires_at: float = time.time() + ttl

    def valid(self) -> bool:  # noqa: D401 – short predicate
        """Return True while the entry hasn’t expired."""
        return time.time() < self.expires_at


# ---------------------------------------------------------------------------
# Main public class
# ---------------------------------------------------------------------------
class InstrumentHandler:
    """
    Encapsulates instrument discovery and provides a minimal in-memory cache.

    Parameters
    ----------
    client : ApiClient
        The shared REST client instance (injected so we can unit-test).
    """

    _TTL_SECONDS: int = 900  # default 15-minute cache for the full universe

    def __init__(self, client=api_client):
        if client is None:
            # Happens only if configuration failed and ApiClient wasn’t built.
            raise OandaError("ApiClient unavailable – check .env configuration.")
        self._client = client
        self._default_account_id: str = settings.account_id
        self._cache: Dict[str, _CacheEntry] = {}  # keyed by account id

    # ---------------------------------------------------------------------
    # Public – list all or a filtered subset
    # ---------------------------------------------------------------------
    @retry()            # auto-retry on network / API errors
    @track_latency      # measure execution time and log at DEBUG level
    def list_instruments(
        self,
        account_id: Optional[AccountID] = None,
        *,
        names: Optional[List[InstrumentName]] = None,
        force_refresh: bool = False,
    ) -> List[Instrument]:
        """
        Return the instrument list for `account_id`.

        Parameters
        ----------
        account_id : str, optional
            If omitted, uses the default ID from .env.
        names : list[str], optional
            If provided, OANDA filters the response to those instruments.
        force_refresh : bool, default False
            Ignore the cache even if it hasn’t expired.

        Notes
        -----
        • The cache is **only** written when we fetch the *full* universe.
        • A filtered call (`names=…`) always bypasses the cache because the API
          already does the subset filtering more efficiently.
        """
        acc_id = account_id or self._default_account_id
        if not acc_id:
            raise ValueError("Account ID must be provided or set in .env.")

        # Serve from cache when possible
        entry = self._cache.get(acc_id)
        if entry and entry.valid() and names is None and not force_refresh:
            logger.debug(
                "Instrument list served from cache (%d entries)", len(entry.payload)
            )
            return entry.payload

        # Build and issue the GET request
        endpoint = f"/v3/accounts/{acc_id}/instruments"
        params = {"instruments": ",".join(names)} if names else None
        logger.info("Fetching instruments for %s …", acc_id[:10] + "…")

        data = self._client.get(endpoint, params=params)

        # Basic shape validation
        if "instruments" not in data or not isinstance(data["instruments"], list):
            raise ParseError("Unexpected payload – missing 'instruments' list.")

        instruments = [Instrument.from_dict(d) for d in data["instruments"]]
        logger.info("Received %d instrument records", len(instruments))

        # Cache only when we fetched the **complete** universe
        if names is None:
            self._cache[acc_id] = _CacheEntry(instruments, self._TTL_SECONDS)

        return instruments

    # ---------------------------------------------------------------------
    # Public – single-instrument convenience wrapper
    # ---------------------------------------------------------------------
    @retry()
    @track_latency
    def get(self, instrument_name: InstrumentName) -> Instrument:
        """
        Fetch a single instrument’s metadata via `/v3/instruments/{name}`.

        Raises
        ------
        ParseError
            If the response JSON structure isn’t recognised.
        """
        endpoint = f"/v3/instruments/{instrument_name}"
        logger.debug("Fetching instrument %s", instrument_name)

        data = self._client.get(endpoint)

        if "instrument" not in data:
            raise ParseError("Unexpected payload – missing 'instrument' key.")

        return Instrument.from_dict(data["instrument"])


# ---------------------------------------------------------------------------
# Singleton instance so caller can just `from instruments.handlers import instrument_handler`
# ---------------------------------------------------------------------------
try:
    instrument_handler: InstrumentHandler | None = InstrumentHandler(api_client)
except OandaError as exc:
    instrument_handler = None   # Keep module importable even if config failed
    logger.error("InstrumentHandler unavailable: %s", exc)
