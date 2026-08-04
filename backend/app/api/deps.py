"""Shared FastAPI dependencies: DB session + authentication/authorization guards.

The backend independently validates authentication and every permission on each
request — the client's claims are never trusted.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import rbac
from app.core.security import decode_token
from app.db.models.user import User
from app.db.session import get_db
from app.services.auth_service import is_denylisted

_bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise _UNAUTHENTICATED

    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise _UNAUTHENTICATED

    if payload.get("type") != "access":
        raise _UNAUTHENTICATED

    jti = payload.get("jti")
    if jti and is_denylisted(jti):
        raise _UNAUTHENTICATED

    sub = payload.get("sub")
    if not sub:
        raise _UNAUTHENTICATED
    try:
        user = db.get(User, uuid.UUID(str(sub)))
    except (ValueError, TypeError):
        raise _UNAUTHENTICATED

    if user is None or not user.is_active:
        raise _UNAUTHENTICATED
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(code: str) -> Callable[..., User]:
    """Dependency factory enforcing that the current user has a permission code."""

    def _dependency(user: CurrentUser) -> User:
        if not rbac.has_permission(user, code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {code}",
            )
        return user

    return _dependency
