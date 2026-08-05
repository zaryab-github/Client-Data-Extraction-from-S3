"""Celery task: run an extraction job in the background."""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.db.models.job import ExtractionJob, JobStatus
from app.db.session import get_session_factory
from app.services import job_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="run_extraction_job", bind=True)
def run_extraction_job(self, job_id: str) -> dict:
    """Load a PENDING job and execute it (extract → zip → store → metadata).

    Idempotent: a job that is not PENDING is not reprocessed (guards against
    duplicate delivery on retry).
    """
    db = get_session_factory()()
    try:
        job = db.scalar(select(ExtractionJob).where(ExtractionJob.job_id == job_id))
        if job is None:
            logger.error("run_extraction_job: job %s not found", job_id)
            return {"job_id": job_id, "status": "NOT_FOUND"}
        if job.status != JobStatus.PENDING:
            logger.info("run_extraction_job: job %s already %s — skipping", job_id, job.status)
            return {"job_id": job_id, "status": job.status}

        job = job_service.run_job(db, job)
        return {"job_id": job_id, "status": job.status}
    finally:
        db.close()
