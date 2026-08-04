"""Shortcode schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ShortcodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    description: str | None = None


class ShortcodeCheckRequest(BaseModel):
    shortcodes: list[str]
