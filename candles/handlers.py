# candles/handlers.py
# Author: Ziggy (OpenAI o3) – 2025-06-19
"""
Thin wrapper for the OANDA candle endpoint:
    GET /v3/instruments/{instrument}/candles
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional

from client import api_client
from utils.decorators import retry, track_latency
from utils.exceptions import ParseError, OandaError
from models.base import InstrumentName  # alias = str

logger = logging.getLogger(__name__)


class CandleHandler:
    """Fetch OHLCV candles and return them as a list[dict]."""

    @retry()
    @track_latency
    def fetch(
        self,
        instrument: InstrumentName,
        *,
        granularity: str = "M5",
        count: int = 200,
        price: str = "M",
    ) -> List[Dict[str, Any]]:
        """
        Parameters
        ----------
        instrument : str   e.g. 'EUR_USD'
        granularity : str  S5 | M1 | M5 | H1 | D | …
        count : int        up to 5000 per request
        price : str        'M' mid (default), 'B', 'A', or 'MBA'

        Returns
        -------
        list[dict]   Raw candle objects from the API
        """
        endpoint = f"/v3/instruments/{instrument}/candles"
        params = dict(granularity=granularity, count=count, price=price)

        data = api_client.get(endpoint, params=params)
        if "candles" not in data or not isinstance(data["candles"], list):
            raise ParseError("Unexpected candle payload from API")

        return data["candles"]


# ---------------------------------------------------------------------------
# Singleton instance (import-ready)
# ---------------------------------------------------------------------------
try:
    candle_handler: Optional[CandleHandler] = CandleHandler()
except OandaError as exc:
    candle_handler = None
    logger.error("CandleHandler unavailable: %s", exc)
