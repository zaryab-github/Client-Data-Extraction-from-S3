"""FastAPI application factory.

Wires configuration, logging, CORS, security headers, a safe error handler, and the
API router.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.router import api_router
from app.config import settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate required configuration at startup (fail fast if misconfigured).
    settings.require()
    yield


def create_app() -> FastAPI:
    configure_logging()

    # Hide interactive API docs in production unless explicitly enabled.
    docs_on = settings.ENABLE_API_DOCS
    app = FastAPI(
        title=settings.APP_NAME,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if docs_on else None,
        redoc_url="/redoc" if docs_on else None,
        openapi_url="/openapi.json" if docs_on else None,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Log the full error server-side; never leak internals to the client.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/", tags=["system"])
    def root() -> dict:
        return {
            "name": settings.APP_NAME,
            "version": __version__,
            "api": settings.API_V1_PREFIX,
        }

    return app


app = create_app()
