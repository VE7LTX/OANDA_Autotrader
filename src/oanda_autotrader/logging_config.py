"""
Structured logging helpers.

Purpose:
- Provide a consistent log format for troubleshooting and metrics.
- Support JSONL output for easy ingestion by downstream tools.
"""

from __future__ import annotations

import json
import logging
import time


class JsonFormatter(logging.Formatter):
    """
    JSONL formatter for structured logs.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    """
    Configure root logging with optional JSONL output.
    """

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if json_output else logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=level.upper(), handlers=[handler])
