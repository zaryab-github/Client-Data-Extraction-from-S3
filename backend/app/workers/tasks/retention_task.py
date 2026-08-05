"""Celery beat task: clean up expired reports."""

from __future__ import annotations

import logging

from app.db.session import get_session_factory
from app.services import retention_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="run_retention")
def run_retention() -> dict:
    db = get_session_factory()()
    try:
        expired = retention_service.cleanup_expired(db)
        return {"expired": expired}
    finally:
        db.close()
