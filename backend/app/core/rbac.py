"""RBAC definitions: permission codes, roles, and their default mappings.

These are the single source of truth used by the seed script and by the
permission-enforcement dependencies.
"""

from __future__ import annotations

from typing import Any

# ── Permission codes ───────────────────────────────────────
JOB_CREATE = "job:create"
REPORT_DOWNLOAD = "report:download"
REPORT_EMAIL = "report:email"
HISTORY_READ = "history:read"
ADMIN_MANAGE_USERS = "admin:manage_users"
ADMIN_MANAGE_SHORTCODES = "admin:manage_shortcodes"

ALL_PERMISSIONS: dict[str, str] = {
    JOB_CREATE: "Create extraction jobs",
    REPORT_DOWNLOAD: "Download generated reports",
    REPORT_EMAIL: "Email generated reports",
    HISTORY_READ: "View extraction history",
    ADMIN_MANAGE_USERS: "Manage users and roles",
    ADMIN_MANAGE_SHORTCODES: "Manage shortcodes and grants",
}

# ── Roles ──────────────────────────────────────────────────
ROLE_ADMIN = "admin"
ROLE_ANALYST = "analyst"
ROLE_VIEWER = "viewer"

ROLE_PERMISSIONS: dict[str, list[str]] = {
    ROLE_ADMIN: list(ALL_PERMISSIONS.keys()),
    ROLE_ANALYST: [JOB_CREATE, REPORT_DOWNLOAD, REPORT_EMAIL, HISTORY_READ],
    ROLE_VIEWER: [REPORT_DOWNLOAD, HISTORY_READ],
}

ROLE_DESCRIPTIONS: dict[str, str] = {
    ROLE_ADMIN: "Full administrative access",
    ROLE_ANALYST: "Create and retrieve extractions for authorized shortcodes",
    ROLE_VIEWER: "Read-only access to own history and reports",
}


# ── Helpers (duck-typed on the User ORM object) ────────────
def user_permission_codes(user: Any) -> set[str]:
    """Return the set of permission codes granted to the user's role."""
    return {p.code for p in user.role.permissions}


def is_admin(user: Any) -> bool:
    return user.role.name == ROLE_ADMIN


def has_permission(user: Any, code: str) -> bool:
    return is_admin(user) or code in user_permission_codes(user)
