"""Logging configuration.

Minimal structured-ish logging for Phase 1. Log level comes from .env.
Secret-scrubbing filters are added in later phases.
"""

from __future__ import annotations

import logging

from app.config import settings


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
