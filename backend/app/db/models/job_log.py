"""Per-job log lines (streamed to the UI as a live console)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class JobLog(Base):
    __tablename__ = "job_logs"

    # Global auto-increment id → simple incremental fetch (?after_id=N).
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("extraction_jobs.job_id", ondelete="CASCADE"), index=True
    )
    level: Mapped[str] = mapped_column(String(16), default="INFO")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
