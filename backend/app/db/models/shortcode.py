"""Shortcode model.

A shortcode is a client identifier that is matched against a column inside the CSV
files (default column ``source_addr``, e.g. value ``8990``). The optional S3 fields
allow per-client overrides of where the daily files live; both fall back to the
``.env`` templates when null. (Used from Phase 4.)
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Shortcode(Base):
    __tablename__ = "shortcodes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    s3_prefix: Mapped[str | None] = mapped_column(String(512), default=None)
    s3_file_template: Mapped[str | None] = mapped_column(String(255), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
