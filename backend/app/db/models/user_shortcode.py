"""User-to-shortcode permission (row-level authorization).

This table is the authority for "which shortcodes a user may extract".
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class UserShortcodePermission(Base):
    __tablename__ = "user_shortcode_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "shortcode_id", name="uq_user_shortcode"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    shortcode_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shortcodes.id", ondelete="CASCADE"), index=True
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), default=None
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc
    )
