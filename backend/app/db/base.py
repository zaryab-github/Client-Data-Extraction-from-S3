"""SQLAlchemy declarative base.

Phase 1 defines only the base + metadata. ORM models (users, roles, shortcodes,
jobs, etc.) are added in later phases — no business models here yet.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""
    pass
