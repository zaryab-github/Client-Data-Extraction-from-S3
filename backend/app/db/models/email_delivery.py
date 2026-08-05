"""Email delivery record (Phase 8)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmailStatus:
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class EmailMethod:
    ATTACHMENT = "attachment"
    LINK = "link"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class EmailDelivery(Base):
    __tablename__ = "email_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("extraction_jobs.job_id", ondelete="CASCADE"), index=True
    )
    recipient: Mapped[str] = mapped_column(String(320))
    method: Mapped[str | None] = mapped_column(String(20), default=None)
    status: Mapped[str] = mapped_column(String(20), default=EmailStatus.PENDING, index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
