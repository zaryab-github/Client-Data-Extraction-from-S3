"""Seed script: RBAC roles/permissions, the first admin, and optional demo data.

Run after migrations:
    python -m app.scripts.seed

Idempotent — safe to run repeatedly. All credentials come from .env
(FIRST_ADMIN_EMAIL / FIRST_ADMIN_PASSWORD / SEED_DEMO_DATA).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core import rbac
from app.core.security import hash_password
from app.db.models.role import Permission, Role
from app.db.models.shortcode import Shortcode
from app.db.models.user import User
from app.db.models.user_shortcode import UserShortcodePermission
from app.db.session import get_session_factory

logger = logging.getLogger(__name__)


# ── Reusable helpers (also used by tests) ──────────────────
def ensure_rbac(db: Session) -> dict[str, Role]:
    """Create all permissions, roles, and their mappings if missing."""
    perms: dict[str, Permission] = {}
    for code, desc in rbac.ALL_PERMISSIONS.items():
        p = db.scalar(select(Permission).where(Permission.code == code))
        if p is None:
            p = Permission(code=code, description=desc)
            db.add(p)
        perms[code] = p
    db.flush()

    roles: dict[str, Role] = {}
    for name, codes in rbac.ROLE_PERMISSIONS.items():
        role = db.scalar(select(Role).where(Role.name == name))
        if role is None:
            role = Role(name=name, description=rbac.ROLE_DESCRIPTIONS.get(name))
            db.add(role)
        role.permissions = [perms[c] for c in codes]
        roles[name] = role
    db.flush()
    return roles


def upsert_user(
    db: Session,
    email: str,
    password: str,
    role_name: str,
    full_name: str | None = None,
    is_active: bool = True,
) -> User:
    user = db.scalar(select(User).where(User.email == email))
    role = db.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        raise ValueError(f"Role '{role_name}' does not exist — run ensure_rbac first.")
    if user is None:
        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            is_active=is_active,
            role_id=role.id,
        )
        db.add(user)
    else:
        user.role_id = role.id
        user.is_active = is_active
    db.flush()
    return user


def upsert_shortcode(
    db: Session, code: str, name: str, description: str | None = None
) -> Shortcode:
    sc = db.scalar(select(Shortcode).where(Shortcode.code == code))
    if sc is None:
        sc = Shortcode(code=code, name=name, description=description)
        db.add(sc)
        db.flush()
    return sc


def grant_shortcode(
    db: Session, user: User, shortcode: Shortcode, granted_by: User | None = None
) -> UserShortcodePermission:
    existing = db.scalar(
        select(UserShortcodePermission).where(
            UserShortcodePermission.user_id == user.id,
            UserShortcodePermission.shortcode_id == shortcode.id,
        )
    )
    if existing:
        return existing
    grant = UserShortcodePermission(
        user_id=user.id,
        shortcode_id=shortcode.id,
        granted_by=granted_by.id if granted_by else None,
    )
    db.add(grant)
    db.flush()
    return grant


# ── Entry point ────────────────────────────────────────────
def run_seed() -> None:
    session = get_session_factory()()
    try:
        ensure_rbac(session)
        print("RBAC roles/permissions ensured.")

        if settings.FIRST_ADMIN_EMAIL and settings.FIRST_ADMIN_PASSWORD:
            upsert_user(
                session,
                email=settings.FIRST_ADMIN_EMAIL,
                password=settings.FIRST_ADMIN_PASSWORD,
                role_name=rbac.ROLE_ADMIN,
                full_name="Administrator",
            )
            print(f"Admin user ensured: {settings.FIRST_ADMIN_EMAIL}")
        else:
            print(
                "FIRST_ADMIN_EMAIL/FIRST_ADMIN_PASSWORD not set — skipped admin creation."
            )

        if settings.SEED_DEMO_DATA:
            upsert_shortcode(session, "8990", "Demo client 8990")
            upsert_shortcode(session, "1234", "Demo client 1234")
            print("Demo shortcodes ensured: 8990, 1234")

        session.commit()
        print("Seed complete.")
    finally:
        session.close()


if __name__ == "__main__":
    run_seed()
