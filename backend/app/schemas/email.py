"""Email delivery schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr


class EmailRequest(BaseModel):
    # Defaults to the requesting user's own email if omitted.
    recipient: EmailStr | None = None


class EmailDeliveryOut(BaseModel):
    id: str
    job_id: str
    recipient: str
    method: str | None = None
    status: str
    error: str | None = None
    created_at: datetime
    sent_at: datetime | None = None
