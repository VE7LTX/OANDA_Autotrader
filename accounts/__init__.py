# accounts/__init__.py – rewritten with inline comments
# Author: Ziggy (ChatGPT o3)
# Last Updated: 2025‑06‑19
"""Public façade for the *accounts* sub‑module.

Why rewrite?
* The original version used a **relative import** (`from ..models.account …`) which
  breaks if *accounts* lives at repo root (flat layout).  Absolute imports are
  safer in a single‑package project.
* Added inline comments explaining (a) the wildcard export list and (b) why we
  expose a pre‑instantiated `account_handler` singleton.
"""

# ---------------------------------------------------------------------------
# Absolute imports – the parent directory is on PYTHONPATH when you launch
# `python main.py`, so we import modules directly.
# ---------------------------------------------------------------------------

from accounts.handlers import account_handler, AccountHandler  # noqa: F401 – re‑export
from models.account import Account, AccountSummary, Instrument  # noqa: F401 – tidy re‑export

# ---------------------------------------------------------------------------
# __all__ tells `from accounts import *` which names to pull into the caller’s
# namespace.  It also serves as documentation for IDEs & Sphinx.
# ---------------------------------------------------------------------------

__all__ = [
    # handler class & singleton
    "AccountHandler",
    "account_handler",
    # dataclasses
    "Account",
    "AccountSummary",
    "Instrument",
]
