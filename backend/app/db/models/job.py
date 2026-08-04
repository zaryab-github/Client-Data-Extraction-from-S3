"""Extraction job + report metadata models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JobStatus:
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class ExtractionJob(Base):
    __tablename__ = "extraction_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Public, human-friendly identifier (EXT-YYYYMMDD-NNNNNN). Never the PK.
    job_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.PENDING, index=True)

    requested_shortcodes: Mapped[list] = mapped_column(JSON, default=list)
    date_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    date_to: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(20), default="web")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)


class ReportMetadata(Base):
    __tablename__ = "report_metadata"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("extraction_jobs.job_id", ondelete="CASCADE"), unique=True, index=True
    )

    csv_filename: Mapped[str] = mapped_column(String(255))
    zip_filename: Mapped[str] = mapped_column(String(255))
    metadata_filename: Mapped[str] = mapped_column(String(255))
    # Server-side paths (never exposed to clients).
    csv_path: Mapped[str] = mapped_column(String(1024))
    zip_path: Mapped[str] = mapped_column(String(1024))
    metadata_json_path: Mapped[str] = mapped_column(String(1024))

    csv_row_count: Mapped[int] = mapped_column(Integer, default=0)
    source_file_count: Mapped[int] = mapped_column(Integer, default=0)
    missing_file_count: Mapped[int] = mapped_column(Integer, default=0)
    rows_scanned: Mapped[int] = mapped_column(Integer, default=0)
    bad_timestamp_rows: Mapped[int] = mapped_column(Integer, default=0)

    zip_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
