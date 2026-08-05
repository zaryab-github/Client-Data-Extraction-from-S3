"""Admin management schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr


# ── Users ──────────────────────────────────────────────────
class AdminUserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str | None = None
    role: str
    is_active: bool
    created_at: datetime | None = None
    last_login_at: datetime | None = None


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    role: str = "analyst"
    is_active: bool = True


class AdminUserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None


class RoleOut(BaseModel):
    name: str
    description: str | None = None
    permissions: list[str]


# ── Shortcodes ─────────────────────────────────────────────
class AdminShortcodeOut(BaseModel):
    id: str
    code: str
    name: str
    description: str | None = None
    s3_prefix: str | None = None
    s3_file_template: str | None = None
    is_active: bool


class AdminShortcodeCreate(BaseModel):
    code: str
    name: str
    description: str | None = None
    s3_prefix: str | None = None
    s3_file_template: str | None = None


class AdminShortcodeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    s3_prefix: str | None = None
    s3_file_template: str | None = None
    is_active: bool | None = None


# ── Grants ─────────────────────────────────────────────────
class GrantRequest(BaseModel):
    shortcodes: list[str]


# ── Audit ──────────────────────────────────────────────────
class AuditOut(BaseModel):
    id: str
    user_email: str | None = None
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    ip_address: str | None = None
    created_at: datetime
    details: dict | None = None
