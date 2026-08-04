"""Health and readiness endpoints.

- ``/health``  — liveness: the process is up (no dependencies checked).
- ``/ready``   — readiness: checks configured dependencies (DB, Redis) are
  reachable. Returns 503 if any dependency is down.

These contain no business logic; they only verify the foundation wiring.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import __version__
from app.config import settings
from app.core import redis as redis_layer
from app.db import session as db_layer

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    """Liveness probe — always OK if the process is running."""
    return {"status": "ok", "app": settings.APP_NAME, "version": __version__}


@router.get("/ready")
def ready() -> JSONResponse:
    """Readiness probe — verifies DB and Redis connectivity."""
    checks: dict[str, str] = {}
    healthy = True

    try:
        db_layer.check_connection()
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report, don't crash the probe
        checks["database"] = f"error: {type(exc).__name__}"
        healthy = False

    try:
        redis_layer.check_connection()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {type(exc).__name__}"
        healthy = False

    status_code = 200 if healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ready" if healthy else "degraded", "checks": checks},
    )
