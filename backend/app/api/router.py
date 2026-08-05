"""Aggregate API router.

Mounts system (health/ready), auth, and shortcodes routes under the versioned
prefix. Feature routers (jobs, reports, history, admin, internal) are added in
later phases.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import admin, auth, health, jobs, reports, shortcodes

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(shortcodes.router)
api_router.include_router(jobs.router)
api_router.include_router(reports.router)
api_router.include_router(admin.router)
