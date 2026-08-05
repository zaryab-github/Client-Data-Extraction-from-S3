"""Job submission + status routes (Phase 6).

- POST /jobs         → validate + authorize + create job (PENDING) + enqueue Celery
- GET  /jobs         → list the caller's jobs (admins: all)
- GET  /jobs/{id}    → job status + report metadata (ownership enforced)

Authorization is enforced on the backend for every request:
  * `job:create` permission (RBAC)
  * every requested shortcode must be granted (shortcode-level)
  * non-admins can only see their own jobs
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_permission
from app.config import settings
from app.core import rbac
from app.core.rbac import JOB_CREATE
from app.db.models.job import ExtractionJob, ReportMetadata
from app.db.session import get_db
from app.schemas.job import JobCreateRequest, JobOut, ReportOut
from app.services import audit_service, job_service
from app.services.authorization import authorize_shortcodes
from app.services.extraction_service import ExtractionRequest

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _report_out(report: ReportMetadata | None) -> ReportOut | None:
    if report is None:
        return None
    return ReportOut(
        csv_row_count=report.csv_row_count,
        source_file_count=report.source_file_count,
        missing_file_count=report.missing_file_count,
        rows_scanned=report.rows_scanned,
        bad_timestamp_rows=report.bad_timestamp_rows,
        zip_size_bytes=report.zip_size_bytes,
        checksum_sha256=report.checksum_sha256,
        expires_at=report.expires_at,
    )


def _job_out(db: Session, job: ExtractionJob) -> JobOut:
    report = db.scalar(select(ReportMetadata).where(ReportMetadata.job_id == job.job_id))
    return JobOut(
        job_id=job.job_id,
        status=job.status,
        requested_shortcodes=list(job.requested_shortcodes),
        date_from=job.date_from,
        date_to=job.date_to,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error_message=job.error_message,
        report=_report_out(report),
    )


@router.post("", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def create_job(
    payload: JobCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[object, Depends(require_permission(JOB_CREATE))],
) -> JobOut:
    # Validate range.
    if payload.date_from > payload.date_to:
        raise HTTPException(status_code=400, detail="date_from must be on or before date_to.")
    span_days = (payload.date_to.date() - payload.date_from.date()).days + 1
    if span_days > settings.MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"Date range too large ({span_days} days); max is {settings.MAX_RANGE_DAYS}.",
        )

    # Backend-enforced shortcode authorization (raises 403 if any not granted).
    try:
        authorize_shortcodes(db, user, payload.shortcodes)
    except HTTPException:
        audit_service.record(
            db, audit_service.AUTHZ_DENY, user=user, resource_type="job",
            request=request, details={"shortcodes": payload.shortcodes},
        )
        raise

    job = job_service.create_job(
        db,
        user,
        ExtractionRequest(
            shortcodes=payload.shortcodes,
            date_from=payload.date_from,
            date_to=payload.date_to,
        ),
    )
    audit_service.record(
        db, audit_service.JOB_CREATE, user=user, resource_type="job",
        resource_id=job.job_id, request=request,
        details={"shortcodes": payload.shortcodes},
    )

    # Enqueue background processing (imported lazily to avoid import cost at startup).
    from app.workers.tasks.extraction_task import run_extraction_job

    run_extraction_job.delay(job.job_id)

    db.refresh(job)
    return _job_out(db, job)


@router.get("", response_model=list[JobOut])
def list_jobs(
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[JobOut]:
    stmt = select(ExtractionJob).order_by(ExtractionJob.created_at.desc())
    if not rbac.is_admin(user):
        stmt = stmt.where(ExtractionJob.user_id == user.id)
    if status_filter:
        stmt = stmt.where(ExtractionJob.status == status_filter.upper())
    stmt = stmt.limit(min(limit, 200)).offset(offset)
    return [_job_out(db, j) for j in db.scalars(stmt).all()]


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> JobOut:
    job = db.scalar(select(ExtractionJob).where(ExtractionJob.job_id == job_id))
    # Non-owner (non-admin) gets 404 — don't leak existence.
    if job is None or (job.user_id != user.id and not rbac.is_admin(user)):
        raise HTTPException(status_code=404, detail="Job not found.")
    audit_service.record(
        db, audit_service.JOB_ACCESS, user=user, resource_type="job",
        resource_id=job.job_id, request=request,
    )
    return _job_out(db, job)
