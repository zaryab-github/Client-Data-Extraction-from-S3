"""Unique Job ID generation.

Default format `EXT-YYYYMMDD-NNNNNN` (per-day incrementing sequence). The `uuid4`
strategy yields a non-enumerable `EXT-YYYYMMDD-<hex>` instead.

The sequence is not concurrency-proof on its own; the caller inserts with a unique
constraint on job_id and retries on collision.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.job import ExtractionJob


def _today_prefix(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"EXT-{now:%Y%m%d}-"


def generate_job_id(db: Session, now: datetime | None = None) -> str:
    prefix = _today_prefix(now)
    if settings.JOB_ID_STRATEGY.lower() == "uuid4":
        return f"{prefix}{uuid.uuid4().hex[:10].upper()}"

    # ext_seq: next sequence for today.
    existing = db.scalars(
        select(ExtractionJob.job_id).where(ExtractionJob.job_id.like(f"{prefix}%"))
    ).all()
    max_seq = 0
    for jid in existing:
        tail = jid.rsplit("-", 1)[-1]
        if tail.isdigit():
            max_seq = max(max_seq, int(tail))
    return f"{prefix}{max_seq + 1:06d}"
