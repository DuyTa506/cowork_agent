"""Logging setup shared by the API and the worker."""
from __future__ import annotations

import logging

from .config import LOG_LEVEL


def configure_logging() -> None:
    """Sends application logs to stderr in one line per record; idempotent."""
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(LOG_LEVEL)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per request would drown the useful logs
