"""Job-related request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class JobCreateRequest(BaseModel):
    shortcodes: list[str]
    date_from: datetime
    date_to: datetime


class ReportOut(BaseModel):
    csv_row_count: int
    source_file_count: int
    missing_file_count: int
    rows_scanned: int
    bad_timestamp_rows: int
    zip_size_bytes: int
    checksum_sha256: str | None = None
    expires_at: datetime | None = None


class JobOut(BaseModel):
    job_id: str
    status: str
    requested_shortcodes: list[str]
    date_from: datetime
    date_to: datetime
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    report: ReportOut | None = None
