"""Shortcode routes.

- ``GET /shortcodes``          → only the shortcodes the user is authorized for.
- ``GET /shortcodes/{code}``   → the shortcode if authorized, else 403/404.
- ``POST /shortcodes/check``   → validate a selection (all-or-nothing) — useful for
  the frontend before creating a job (real extraction lands in Phase 5).

Every endpoint enforces authorization on the backend, independent of the client.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.db.models.shortcode import Shortcode
from app.db.session import get_db
from app.schemas.shortcode import ShortcodeCheckRequest, ShortcodeOut
from app.services.authorization import authorize_shortcodes, get_authorized_shortcodes

router = APIRouter(prefix="/shortcodes", tags=["shortcodes"])


@router.get("", response_model=list[ShortcodeOut])
def list_authorized_shortcodes(
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[ShortcodeOut]:
    shortcodes = get_authorized_shortcodes(db, user)
    return [
        ShortcodeOut(id=str(s.id), code=s.code, name=s.name, description=s.description)
        for s in shortcodes
    ]


@router.post("/check")
def check_shortcodes(
    payload: ShortcodeCheckRequest,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    # Raises 403 if the user is not authorized for every requested shortcode.
    resolved = authorize_shortcodes(db, user, payload.shortcodes)
    return {"authorized": True, "shortcodes": [s.code for s in resolved]}


@router.get("/{code}", response_model=ShortcodeOut)
def get_shortcode(
    code: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> ShortcodeOut:
    # Authorization first: this raises 403 if the user isn't granted `code`
    # (and also 403 if the code doesn't exist, so existence isn't leaked).
    authorize_shortcodes(db, user, [code])
    s = db.scalar(select(Shortcode).where(Shortcode.code == code))
    return ShortcodeOut(id=str(s.id), code=s.code, name=s.name, description=s.description)
