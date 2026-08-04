"""Aggregate API router.

Phase 1 mounts only the system (health/ready) routes. Feature routers
(auth, shortcodes, jobs, reports, history, admin, internal) are added in later
phases under the versioned prefix.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import health

api_router = APIRouter()
api_router.include_router(health.router)
