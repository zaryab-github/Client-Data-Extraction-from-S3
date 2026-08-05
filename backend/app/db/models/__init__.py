"""ORM models package.

Importing every model here ensures they are registered on ``Base.metadata`` for
Alembic autogeneration and ``create_all``.
"""

from app.db.models.audit import AuditLog
from app.db.models.job import ExtractionJob, JobStatus, ReportMetadata
from app.db.models.job_log import JobLog
from app.db.models.role import Permission, Role, role_permissions
from app.db.models.shortcode import Shortcode
from app.db.models.user import User
from app.db.models.user_shortcode import UserShortcodePermission

__all__ = [
    "Permission",
    "Role",
    "role_permissions",
    "Shortcode",
    "User",
    "UserShortcodePermission",
    "ExtractionJob",
    "ReportMetadata",
    "JobStatus",
    "AuditLog",
    "JobLog",
]
