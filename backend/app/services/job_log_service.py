"""Per-job log lines.

`append` uses its own short-lived session and commits immediately, so log lines are
visible to the polling UI *while* the job is still running (independent of the
worker's main transaction). Best-effort — logging never breaks a job.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.job_log import JobLog
from app.db.session import get_session_factory

logger = logging.getLogger(__name__)


def append(job_id: str, message: str, level: str = "INFO") -> None:
    db = get_session_factory()()
    try:
        db.add(JobLog(job_id=job_id, message=message, level=level))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.debug("Failed to append job log for %s", job_id)
    finally:
        db.close()


def get_logs(db: Session, job_id: str, after_id: int = 0, limit: int = 1000) -> list[JobLog]:
    return list(
        db.scalars(
            select(JobLog)
            .where(JobLog.job_id == job_id, JobLog.id > after_id)
            .order_by(JobLog.id)
            .limit(limit)
        ).all()
    )
