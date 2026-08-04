"""Authentication service: credential verification and login rate limiting.

Rate limiting and the token denylist use Redis but are best-effort: if Redis is
unavailable they fail open (do not block logins) rather than crash the request.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.redis import get_redis
from app.core.security import verify_password
from app.db.models.user import User

logger = logging.getLogger(__name__)


def authenticate(db: Session, email: str, password: str) -> User | None:
    """Return the user if email exists, is active, and the password matches."""
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def login_rate_limited(identifier: str) -> bool:
    """Return True if this identifier has exceeded the login attempt limit."""
    key = f"login_attempts:{identifier}"
    try:
        r = get_redis()
        count = r.incr(key)
        if count == 1:
            r.expire(key, settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS)
        return count > settings.LOGIN_RATE_LIMIT_ATTEMPTS
    except Exception:  # Redis down → do not block auth
        logger.warning("Login rate-limit check skipped (Redis unavailable)")
        return False


def reset_login_attempts(identifier: str) -> None:
    try:
        get_redis().delete(f"login_attempts:{identifier}")
    except Exception:
        pass


# ── Token denylist (logout) ────────────────────────────────
def denylist_token(jti: str, ttl_seconds: int) -> None:
    try:
        get_redis().setex(f"denylist:{jti}", max(ttl_seconds, 1), "1")
    except Exception:
        logger.warning("Could not denylist token (Redis unavailable)")


def is_denylisted(jti: str) -> bool:
    try:
        return bool(get_redis().exists(f"denylist:{jti}"))
    except Exception:
        # Fail open: Redis outage should not lock everyone out.
        return False
