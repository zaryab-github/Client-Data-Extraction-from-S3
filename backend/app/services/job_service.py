"""Job orchestration (Phase 5, synchronous).

Creates an extraction job with a unique Job ID, runs the extraction engine, packages
the result (CSV + ZIP + metadata.json) into local storage, and records report
metadata in the database.

Phase 6 will move the run step into a Celery worker; the storage/report structure
here stays the same.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.job_id import generate_job_id
from app.db.models.job import ExtractionJob, JobStatus, ReportMetadata
from app.db.models.user import User
from app.services import storage_service, zip_service
from app.services.extraction_service import ExtractionRequest, run_extraction

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_job(db: Session, user: User, request: ExtractionRequest, source: str = "web") -> ExtractionJob:
    """Insert a new job row with a unique Job ID (retrying on collision)."""
    for _ in range(5):
        job_id = generate_job_id(db)
        job = ExtractionJob(
            job_id=job_id,
            user_id=user.id,
            status=JobStatus.PENDING,
            requested_shortcodes=list(request.shortcodes),
            destination_addrs=list(request.destinations) or None,
            date_from=request.date_from,
            date_to=request.date_to,
            source=source,
        )
        db.add(job)
        try:
            db.commit()
            db.refresh(job)
            return job
        except IntegrityError:
            db.rollback()  # job_id collided; try the next sequence
    raise RuntimeError("Could not allocate a unique Job ID after several attempts.")


def _expires_at(created: datetime) -> datetime | None:
    days = settings.REPORT_RETENTION_DAYS
    return created + timedelta(days=days) if days and days > 0 else None


def run_job(db: Session, job: ExtractionJob) -> ExtractionJob:
    """Execute a PENDING job: extract → zip → store → record metadata."""
    request = ExtractionRequest(
        shortcodes=list(job.requested_shortcodes),
        date_from=job.date_from,
        date_to=job.date_to,
        destinations=list(job.destination_addrs) if job.destination_addrs else [],
    )
    job.status = JobStatus.PROCESSING
    job.started_at = _now()
    db.commit()

    tmp = storage_service.new_temp_dir(job.job_id)
    try:
        csv_path = tmp / storage_service.CSV_FILENAME
        stats = run_extraction(request, str(csv_path))

        completed = _now()
        expires = _expires_at(job.created_at or completed)

        zip_name = storage_service.zip_filename(job.job_id)
        zip_path = tmp / zip_name
        zip_service.create_zip(zip_path, [(storage_service.CSV_FILENAME, csv_path)])
        checksum = zip_service.sha256_file(zip_path)
        zip_size = zip_path.stat().st_size

        metadata = {
            "job_id": job.job_id,
            "user": _user_email(db, job.user_id),
            "shortcodes": list(job.requested_shortcodes),
            "destination_addrs": list(job.destination_addrs) if job.destination_addrs else [],
            "date_from": job.date_from.isoformat(),
            "date_to": job.date_to.isoformat(),
            "files_processed": stats.files_processed,
            "missing_files": stats.missing_dates,
            "records_extracted": stats.rows_matched,
            "rows_scanned": stats.rows_scanned,
            "bad_timestamp_rows": stats.bad_timestamp_rows,
            "malformed_rows": stats.malformed_rows,
            "source_files": stats.source_keys,
            "created_at": (job.created_at or completed).isoformat(),
            "completed_at": completed.isoformat(),
            "csv_filename": storage_service.CSV_FILENAME,
            "zip_filename": zip_name,
            "metadata_filename": storage_service.METADATA_FILENAME,
            "zip_size_bytes": zip_size,
            "checksum_sha256": checksum,
            "expires_at": expires.isoformat() if expires else None,
            "status": JobStatus.COMPLETED,
        }
        meta_path = tmp / storage_service.METADATA_FILENAME
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        final_dir = storage_service.publish(tmp, job.job_id)

        report = ReportMetadata(
            job_id=job.job_id,
            csv_filename=storage_service.CSV_FILENAME,
            zip_filename=zip_name,
            metadata_filename=storage_service.METADATA_FILENAME,
            csv_path=str(final_dir / storage_service.CSV_FILENAME),
            zip_path=str(final_dir / zip_name),
            metadata_json_path=str(final_dir / storage_service.METADATA_FILENAME),
            csv_row_count=stats.rows_matched,
            source_file_count=stats.files_processed,
            source_files=list(stats.source_keys),
            missing_file_count=stats.files_missing,
            rows_scanned=stats.rows_scanned,
            bad_timestamp_rows=stats.bad_timestamp_rows,
            zip_size_bytes=zip_size,
            checksum_sha256=checksum,
            expires_at=expires,
        )
        db.add(report)
        job.status = JobStatus.COMPLETED
        job.finished_at = completed
        db.commit()
        logger.info("Job %s COMPLETED: %d rows", job.job_id, stats.rows_matched)
        return job

    except Exception as exc:  # noqa: BLE001
        db.rollback()
        storage_service.delete_job_dir(job.job_id)  # remove any partial output
        shutil.rmtree(tmp, ignore_errors=True)      # best-effort temp cleanup
        job.status = JobStatus.FAILED
        job.finished_at = _now()
        job.error_message = f"{type(exc).__name__}: {exc}"
        db.commit()
        logger.exception("Job %s FAILED", job.job_id)
        return job


def create_and_run(db: Session, user: User, request: ExtractionRequest, source: str = "web") -> ExtractionJob:
    job = create_job(db, user, request, source=source)
    return run_job(db, job)


def _user_email(db: Session, user_id) -> str:
    user = db.get(User, user_id)
    return user.email if user else str(user_id)
