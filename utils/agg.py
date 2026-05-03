# utils/agg.py
"""
CandleAggregator – roll raw OANDA PRICE ticks into time-boxed OHLC bars.

Usage
-----
agg = CandleAggregator(window_secs=5)
agg.add_tick(price_msg)   # call once per PRICE tick
bars = agg.flush_ready()  # returns *complete* bars (list[dict])
"""

from __future__ import annotations
import math
import time
from typing import List, Dict, Any


class CandleAggregator:
    def __init__(self, window_secs: int = 5):
        self.window = window_secs
        self._reset()

    # ─── public ──────────────────────────────────────────────────────────
    def add_tick(self, msg: Dict[str, Any]):
        """Feed one PRICE message (as parsed JSON dict)."""
        px = float(msg["bids"][0]["price"])     # use mid≈bid for demo
        ts = math.floor(time.time())            # epoch-sec for binning

        if self.bar["start"] is None:
            # first tick → start new bar
            self.bar.update(start=ts, open=px, high=px, low=px, close=px)
            return

        if ts - self.bar["start"] < self.window:
            # still inside current bucket → update extremes & close
            self.bar["high"] = max(self.bar["high"], px)
            self.bar["low"]  = min(self.bar["low"],  px)
            self.bar["close"] = px
        else:
            # bucket completed → push to list and start a new one
            self.completed.append(self.bar.copy())
            self._reset(start=ts, open_=px)

    def flush_ready(self) -> List[Dict[str, Any]]:
        """Return and clear the list of completed bars."""
        out, self.completed = self.completed, []
        return out

    # ─── internals ───────────────────────────────────────────────────────
    def _reset(self, start: int | None = None, open_: float | None = None):
        self.bar = dict(start=start, open=open_, high=open_, low=open_, close=open_)
        self.completed: List[Dict[str, Any]] = []
