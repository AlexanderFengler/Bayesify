"""Logging helpers for the API layer."""

from __future__ import annotations

import logging


def app_logger() -> logging.Logger:
    logger = logging.getLogger("bayesify.api")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
