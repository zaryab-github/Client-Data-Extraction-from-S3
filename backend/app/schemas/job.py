"""Job-related request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class JobLogOut(BaseModel):
    id: int
    level: str
    message: str
    created_at: datetime


class JobCreateRequest(BaseModel):
    shortcodes: list[str]
    date_from: datetime
    date_to: datetime
    # Optional: further restrict to these destination_addr values.
    destinations: list[str] = []


class ReportOut(BaseModel):
    csv_row_count: int
    source_file_count: int
    source_files: list[str] | None = None
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
    destination_addrs: list[str] | None = None
    date_from: datetime
    date_to: datetime
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    report: ReportOut | None = None
