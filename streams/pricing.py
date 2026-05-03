# streams/pricing.py
# Author : Ziggy (OpenAI o3) — 2025-06-19
"""
PricingStreamWorker
===================
Long-lived GET /v3/accounts/{id}/pricing/stream → yields mid price ticks.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from typing import List, Dict, Any, Optional

import requests

from config import settings
from utils.exceptions import OandaError, StreamConnectionError

logger = logging.getLogger(__name__)


class PricingStreamWorker(threading.Thread):
    """
    Opens OANDA’s pricing stream in a background thread and
    pushes each tick (dict) into a thread-safe Queue.

    Parameters
    ----------
    instruments : list[str]  e.g. ["EUR_USD"]
    out_queue   : queue.Queue
    """

    def __init__(
        self,
        instruments: List[str],
        out_queue: queue.Queue,
        *,
        account_id: Optional[str] = None,
    ):
        super().__init__(daemon=True)
        self.instruments = instruments
        self.out_q = out_queue
        self._account_id = account_id or settings.account_id
        self._stop_flag = threading.Event()

    # ── public ─────────────────────────────────────────────────────────
    def stop(self):
        """Signal the thread to exit."""
        self._stop_flag.set()

    # ── thread run loop ────────────────────────────────────────────────
    def run(self):
        endpoint = (
            f"{settings.stream_url}/v3/accounts/{self._account_id}/pricing/stream"
        )
        params = {"instruments": ",".join(self.instruments)}
        headers = settings.get_auth_headers()

        logger.info("Opening pricing stream for %s", params["instruments"])
        try:
            with requests.get(
                endpoint, headers=headers, params=params, stream=True, timeout=30
            ) as resp:
                if resp.status_code != 200:
                    raise StreamConnectionError(
                        f"Stream error – HTTP {resp.status_code}: {resp.text[:300]}"
                    )

                for line in resp.iter_lines():
                    if self._stop_flag.is_set():
                        break
                    if not line:
                        continue  # keep-alive heartbeat
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug("Skipping malformed line: %s", line[:120])
                        continue
                    if msg.get("type") != "PRICE":
                        continue  # heartbeat or other msg
                    self.out_q.put(msg)  # non-blocking (Queue is thread-safe)

        except requests.RequestException as exc:
            logger.error("Pricing stream lost: %s", exc)
            raise StreamConnectionError from exc

        logger.info("Pricing stream closed.")
