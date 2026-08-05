"""Report download routes (Phase 7).

- GET /reports/{job_id}/download-token → short-lived signed token (auth required)
- GET /reports/{job_id}/download        → stream the ZIP. Accepts either a Bearer
  access token OR a `?token=` download token, so the browser can download natively
  (streamed to disk) without buffering the whole file in memory.

The filesystem path is resolved server-side from the DB record and never accepted
from the client (path-traversal safe). Non-owners get 404; expired reports 410.
"""

from __future__ import annotations

import os
import uuid
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.config import settings
from app.core import rbac
from app.core.rbac import REPORT_DOWNLOAD, REPORT_EMAIL
from app.core.security import create_download_token, decode_token
from app.db.models.email_delivery import EmailDelivery, EmailStatus
from app.db.models.job import ExtractionJob, ReportMetadata
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.email import EmailDeliveryOut, EmailRequest
from app.services import audit_service

router = APIRouter(prefix="/reports", tags=["reports"])

_bearer = HTTPBearer(auto_error=False)


def _load_owned(db: Session, job_id: str, user: User) -> tuple[ExtractionJob, ReportMetadata]:
    job = db.scalar(select(ExtractionJob).where(ExtractionJob.job_id == job_id))
    if job is None or (job.user_id != user.id and not rbac.is_admin(user)):
        raise HTTPException(status_code=404, detail="Report not found.")
    report = db.scalar(select(ReportMetadata).where(ReportMetadata.job_id == job_id))
    if report is None:
        raise HTTPException(status_code=404, detail="Report not available.")
    return job, report


@router.get("/{job_id}/download-token")
def download_token(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(REPORT_DOWNLOAD))],
) -> dict:
    _load_owned(db, job_id, user)  # ownership + existence check
    return {
        "token": create_download_token(str(user.id), job_id),
        "path": f"/reports/{job_id}/download",
    }


@router.get("/{job_id}/download")
def download_report(
    job_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    token: str | None = None,
):
    # Resolve the user from either a download token (?token=) or a Bearer access token.
    user: User | None = None
    if token:
        try:
            claims = decode_token(token)
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Invalid or expired download link.")
        if claims.get("type") != "download" or claims.get("job_id") != job_id:
            raise HTTPException(status_code=401, detail="Invalid download link.")
        user = _user_from_sub(db, claims.get("sub"))
    elif credentials and credentials.credentials:
        try:
            claims = decode_token(credentials.credentials)
            if claims.get("type") == "access":
                user = _user_from_sub(db, claims.get("sub"))
        except jwt.PyJWTError:
            user = None

    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not rbac.has_permission(user, REPORT_DOWNLOAD):
        raise HTTPException(status_code=403, detail="Missing permission: report:download")

    job, report = _load_owned(db, job_id, user)
    if not os.path.exists(report.zip_path):
        raise HTTPException(status_code=410, detail="Report has expired or been removed.")

    audit_service.record(
        db, audit_service.REPORT_DOWNLOAD, user=user, resource_type="report",
        resource_id=job_id, request=request,
    )

    codes = "-".join(job.requested_shortcodes) if job.requested_shortcodes else "report"
    fname = f"{codes}_{job.date_from:%Y%m%d}_{job.date_to:%Y%m%d}.zip"
    return FileResponse(
        report.zip_path,
        media_type="application/zip",
        filename=fname,
        headers={"X-Checksum-SHA256": report.checksum_sha256 or ""},
    )


def _user_from_sub(db: Session, sub) -> User | None:
    try:
        return db.get(User, uuid.UUID(str(sub)))
    except (ValueError, TypeError):
        return None


# ── Email delivery ─────────────────────────────────────────
def _delivery_out(d: EmailDelivery) -> EmailDeliveryOut:
    return EmailDeliveryOut(
        id=str(d.id), job_id=d.job_id, recipient=d.recipient, method=d.method,
        status=d.status, error=d.error, created_at=d.created_at, sent_at=d.sent_at,
    )


@router.post("/{job_id}/email", response_model=EmailDeliveryOut, status_code=status.HTTP_202_ACCEPTED)
def email_report(
    job_id: str,
    payload: EmailRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(REPORT_EMAIL))],
) -> EmailDeliveryOut:
    if not settings.EMAIL_ENABLED:
        raise HTTPException(status_code=503, detail="Email delivery is not enabled.")
    _load_owned(db, job_id, user)  # ownership + report existence

    recipient = str(payload.recipient) if payload.recipient else user.email
    delivery = EmailDelivery(job_id=job_id, recipient=recipient, status=EmailStatus.PENDING)
    db.add(delivery)
    db.commit()
    db.refresh(delivery)

    audit_service.record(
        db, audit_service.REPORT_EMAIL, user=user, resource_type="report",
        resource_id=job_id, request=request, details={"recipient": recipient},
    )

    from app.workers.tasks.email_task import send_report_email

    send_report_email.delay(str(delivery.id))
    return _delivery_out(delivery)


@router.get("/{job_id}/emails", response_model=list[EmailDeliveryOut])
def list_email_deliveries(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(REPORT_EMAIL))],
) -> list[EmailDeliveryOut]:
    _load_owned(db, job_id, user)
    rows = db.scalars(
        select(EmailDelivery)
        .where(EmailDelivery.job_id == job_id)
        .order_by(EmailDelivery.created_at.desc())
    ).all()
    return [_delivery_out(r) for r in rows]
