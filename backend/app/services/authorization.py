"""Shortcode-level authorization.

The backend independently validates that a user may act on a set of shortcodes,
regardless of what the client sends. Admins are authorized for all active
shortcodes; everyone else only for shortcodes explicitly granted to them.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import is_admin
from app.db.models.shortcode import Shortcode
from app.db.models.user import User
from app.db.models.user_shortcode import UserShortcodePermission


def get_authorized_shortcodes(db: Session, user: User) -> list[Shortcode]:
    """Return the active shortcodes the user is authorized to extract."""
    if is_admin(user):
        return list(
            db.scalars(select(Shortcode).where(Shortcode.is_active.is_(True))).all()
        )
    stmt = (
        select(Shortcode)
        .join(
            UserShortcodePermission,
            UserShortcodePermission.shortcode_id == Shortcode.id,
        )
        .where(
            UserShortcodePermission.user_id == user.id,
            Shortcode.is_active.is_(True),
        )
    )
    return list(db.scalars(stmt).all())


def authorize_shortcodes(
    db: Session, user: User, codes: list[str]
) -> list[Shortcode]:
    """Ensure the user is authorized for EVERY requested shortcode code.

    Returns the resolved Shortcode rows, or raises 403 if any are not granted
    (or do not exist / are inactive). All-or-nothing: no partial authorization.
    """
    if not codes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No shortcodes provided.",
        )
    authorized = {s.code: s for s in get_authorized_shortcodes(db, user)}
    missing = [c for c in codes if c not in authorized]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Not authorized for shortcode(s): {', '.join(missing)}",
        )
    return [authorized[c] for c in codes]
