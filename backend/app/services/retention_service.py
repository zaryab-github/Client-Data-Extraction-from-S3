"""Report retention / cleanup.

Deletes stored artifacts for jobs whose report has passed `expires_at`, marks those
jobs EXPIRED, and clears orphaned temp dirs. Only generated artifacts are removed —
the S3 source is never touched.

Phase 5 provides the cleanup function; Phase 6 schedules it via Celery beat.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.job import ExtractionJob, JobStatus, ReportMetadata
from app.services import storage_service

logger = logging.getLogger(__name__)


def cleanup_expired(db: Session, now: datetime | None = None) -> int:
    """Remove artifacts + mark EXPIRED for reports past their expires_at.

    Returns the number of jobs expired.
    """
    now = now or datetime.now(timezone.utc)
    stmt = (
        select(ExtractionJob, ReportMetadata)
        .join(ReportMetadata, ReportMetadata.job_id == ExtractionJob.job_id)
        .where(
            ReportMetadata.expires_at.is_not(None),
            ReportMetadata.expires_at < now,
            ExtractionJob.status != JobStatus.EXPIRED,
        )
    )
    expired = 0
    for job, _report in db.execute(stmt).all():
        storage_service.delete_job_dir(job.job_id)
        job.status = JobStatus.EXPIRED
        expired += 1

    storage_service.cleanup_orphan_temp_dirs()
    db.commit()
    if expired:
        logger.info("Retention: expired %d report(s)", expired)
    return expired
