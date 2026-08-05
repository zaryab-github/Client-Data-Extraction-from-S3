"""Celery task: send a report email in the background."""

from __future__ import annotations

import logging
import uuid

from app.db.models.email_delivery import EmailDelivery
from app.db.session import get_session_factory
from app.services import email_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="send_report_email")
def send_report_email(delivery_id: str) -> dict:
    db = get_session_factory()()
    try:
        delivery = db.get(EmailDelivery, uuid.UUID(delivery_id))
        if delivery is None:
            logger.error("send_report_email: delivery %s not found", delivery_id)
            return {"delivery_id": delivery_id, "status": "NOT_FOUND"}
        email_service.send_report_email(db, delivery)
        return {"delivery_id": delivery_id, "status": delivery.status}
    finally:
        db.close()
