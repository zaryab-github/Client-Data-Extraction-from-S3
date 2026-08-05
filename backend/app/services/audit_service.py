"""Audit logging helper."""

from __future__ import annotations

import logging

from fastapi import Request
from sqlalchemy.orm import Session

from app.db.models.audit import AuditLog

logger = logging.getLogger(__name__)

# Action constants.
JOB_CREATE = "job.create"
JOB_ACCESS = "job.access"
REPORT_DOWNLOAD = "report.download"
AUTHZ_DENY = "authz.deny"


def record(
    db: Session,
    action: str,
    *,
    user=None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    request: Request | None = None,
    details: dict | None = None,
) -> None:
    """Write an append-only audit entry. Best-effort — never breaks the request."""
    try:
        entry = AuditLog(
            user_id=getattr(user, "id", None),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=request.client.host if (request and request.client) else None,
            user_agent=request.headers.get("user-agent") if request else None,
            details=details,
        )
        db.add(entry)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("Failed to write audit log for action=%s", action)
