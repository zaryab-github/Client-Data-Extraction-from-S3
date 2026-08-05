"""Admin management routes (Phase 7).

Users, roles, shortcodes, user→shortcode grants, and audit logs. Every endpoint is
permission-gated (admin:manage_users / admin:manage_shortcodes) and enforced on the
backend.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core import rbac
from app.core.rbac import ADMIN_MANAGE_SHORTCODES, ADMIN_MANAGE_USERS
from app.core.security import hash_password
from app.db.models.audit import AuditLog
from app.db.models.role import Role
from app.db.models.shortcode import Shortcode
from app.db.models.user import User
from app.db.models.user_shortcode import UserShortcodePermission
from app.db.session import get_db
from app.schemas.admin import (
    AdminShortcodeCreate,
    AdminShortcodeOut,
    AdminShortcodeUpdate,
    AdminUserCreate,
    AdminUserOut,
    AdminUserUpdate,
    AuditOut,
    GrantRequest,
    RoleOut,
)
from app.schemas.shortcode import ShortcodeOut

router = APIRouter(prefix="/admin", tags=["admin"])

ManageUsers = Depends(require_permission(ADMIN_MANAGE_USERS))
ManageShortcodes = Depends(require_permission(ADMIN_MANAGE_SHORTCODES))


def _user_out(u: User) -> AdminUserOut:
    return AdminUserOut(
        id=str(u.id), email=u.email, full_name=u.full_name, role=u.role.name,
        is_active=u.is_active, created_at=u.created_at, last_login_at=u.last_login_at,
    )


def _sc_out(s: Shortcode) -> AdminShortcodeOut:
    return AdminShortcodeOut(
        id=str(s.id), code=s.code, name=s.name, description=s.description,
        s3_prefix=s.s3_prefix, s3_file_template=s.s3_file_template, is_active=s.is_active,
    )


def _get_user_or_404(db: Session, user_id: str) -> User:
    try:
        u = db.get(User, uuid.UUID(user_id))
    except (ValueError, TypeError):
        u = None
    if u is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return u


# ── Users ──────────────────────────────────────────────────
@router.get("/users", response_model=list[AdminUserOut])
def list_users(db: Annotated[Session, Depends(get_db)], _=ManageUsers) -> list[AdminUserOut]:
    return [_user_out(u) for u in db.scalars(select(User).order_by(User.email)).all()]


@router.post("/users", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: AdminUserCreate, db: Annotated[Session, Depends(get_db)], _=ManageUsers
) -> AdminUserOut:
    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail="Email already exists.")
    role = db.scalar(select(Role).where(Role.name == payload.role))
    if role is None:
        raise HTTPException(status_code=400, detail=f"Unknown role: {payload.role}")
    u = User(
        email=payload.email, hashed_password=hash_password(payload.password),
        full_name=payload.full_name, is_active=payload.is_active, role_id=role.id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return _user_out(u)


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: str, payload: AdminUserUpdate,
    db: Annotated[Session, Depends(get_db)], _=ManageUsers,
) -> AdminUserOut:
    u = _get_user_or_404(db, user_id)
    if payload.full_name is not None:
        u.full_name = payload.full_name
    if payload.is_active is not None:
        u.is_active = payload.is_active
    if payload.password:
        u.hashed_password = hash_password(payload.password)
    if payload.role is not None:
        role = db.scalar(select(Role).where(Role.name == payload.role))
        if role is None:
            raise HTTPException(status_code=400, detail=f"Unknown role: {payload.role}")
        u.role_id = role.id
    db.commit()
    db.refresh(u)
    return _user_out(u)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str, db: Annotated[Session, Depends(get_db)], admin=ManageUsers
):
    u = _get_user_or_404(db, user_id)
    if admin.id == u.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")
    # Preserve the audit trail but detach it from the deleted user.
    db.execute(update(AuditLog).where(AuditLog.user_id == u.id).values(user_id=None))
    try:
        db.delete(u)  # shortcode grants cascade-delete
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="User has related records (e.g. jobs). Deactivate the user instead.",
        )
    return None


@router.get("/roles", response_model=list[RoleOut])
def list_roles(db: Annotated[Session, Depends(get_db)], _=ManageUsers) -> list[RoleOut]:
    return [
        RoleOut(name=r.name, description=r.description,
                permissions=sorted(p.code for p in r.permissions))
        for r in db.scalars(select(Role).order_by(Role.name)).all()
    ]


# ── Shortcodes ─────────────────────────────────────────────
@router.get("/shortcodes", response_model=list[AdminShortcodeOut])
def list_shortcodes(db: Annotated[Session, Depends(get_db)], _=ManageShortcodes) -> list[AdminShortcodeOut]:
    return [_sc_out(s) for s in db.scalars(select(Shortcode).order_by(Shortcode.code)).all()]


@router.post("/shortcodes", response_model=AdminShortcodeOut, status_code=status.HTTP_201_CREATED)
def create_shortcode(
    payload: AdminShortcodeCreate, db: Annotated[Session, Depends(get_db)], _=ManageShortcodes
) -> AdminShortcodeOut:
    if db.scalar(select(Shortcode).where(Shortcode.code == payload.code)):
        raise HTTPException(status_code=409, detail="Shortcode already exists.")
    s = Shortcode(
        code=payload.code, name=payload.name, description=payload.description,
        s3_prefix=payload.s3_prefix, s3_file_template=payload.s3_file_template,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _sc_out(s)


@router.patch("/shortcodes/{shortcode_id}", response_model=AdminShortcodeOut)
def update_shortcode(
    shortcode_id: str, payload: AdminShortcodeUpdate,
    db: Annotated[Session, Depends(get_db)], _=ManageShortcodes,
) -> AdminShortcodeOut:
    try:
        s = db.get(Shortcode, uuid.UUID(shortcode_id))
    except (ValueError, TypeError):
        s = None
    if s is None:
        raise HTTPException(status_code=404, detail="Shortcode not found.")
    for field in ("name", "description", "s3_prefix", "s3_file_template", "is_active"):
        val = getattr(payload, field)
        if val is not None:
            setattr(s, field, val)
    db.commit()
    db.refresh(s)
    return _sc_out(s)


# ── Grants ─────────────────────────────────────────────────
@router.get("/users/{user_id}/shortcodes", response_model=list[ShortcodeOut])
def list_user_grants(
    user_id: str, db: Annotated[Session, Depends(get_db)], _=ManageShortcodes
) -> list[ShortcodeOut]:
    u = _get_user_or_404(db, user_id)
    stmt = (
        select(Shortcode)
        .join(UserShortcodePermission, UserShortcodePermission.shortcode_id == Shortcode.id)
        .where(UserShortcodePermission.user_id == u.id)
    )
    return [
        ShortcodeOut(id=str(s.id), code=s.code, name=s.name, description=s.description)
        for s in db.scalars(stmt).all()
    ]


@router.post("/users/{user_id}/shortcodes", status_code=status.HTTP_201_CREATED)
def grant_shortcodes(
    user_id: str, payload: GrantRequest,
    db: Annotated[Session, Depends(get_db)], admin=ManageShortcodes,
) -> dict:
    u = _get_user_or_404(db, user_id)
    granted = []
    for code in payload.shortcodes:
        sc = db.scalar(select(Shortcode).where(Shortcode.code == code))
        if sc is None:
            raise HTTPException(status_code=404, detail=f"Shortcode not found: {code}")
        exists = db.scalar(
            select(UserShortcodePermission).where(
                UserShortcodePermission.user_id == u.id,
                UserShortcodePermission.shortcode_id == sc.id,
            )
        )
        if not exists:
            db.add(UserShortcodePermission(
                user_id=u.id, shortcode_id=sc.id, granted_by=admin.id,
            ))
            granted.append(code)
    db.commit()
    return {"granted": granted}


@router.delete("/users/{user_id}/shortcodes/{code}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_shortcode(
    user_id: str, code: str, db: Annotated[Session, Depends(get_db)], _=ManageShortcodes
):
    u = _get_user_or_404(db, user_id)
    sc = db.scalar(select(Shortcode).where(Shortcode.code == code))
    if sc is not None:
        grant = db.scalar(
            select(UserShortcodePermission).where(
                UserShortcodePermission.user_id == u.id,
                UserShortcodePermission.shortcode_id == sc.id,
            )
        )
        if grant:
            db.delete(grant)
            db.commit()
    return None


# ── Audit logs ─────────────────────────────────────────────
@router.get("/audit-logs", response_model=list[AuditOut])
def list_audit_logs(
    db: Annotated[Session, Depends(get_db)], _=ManageUsers,
    limit: int = 100, offset: int = 0,
) -> list[AuditOut]:
    rows = db.scalars(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500)).offset(offset)
    ).all()
    emails = {u.id: u.email for u in db.scalars(select(User)).all()}
    return [
        AuditOut(
            id=str(r.id), user_email=emails.get(r.user_id), action=r.action,
            resource_type=r.resource_type, resource_id=r.resource_id,
            ip_address=r.ip_address, created_at=r.created_at, details=r.details,
        )
        for r in rows
    ]
