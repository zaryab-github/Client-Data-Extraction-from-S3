"""Test configuration.

Sets a self-contained test environment BEFORE the app config is imported, so the
lightweight Phase 1 checks run without a real .env, database, or Redis server.

- DATABASE_URL uses an in-memory-ish local SQLite file (stdlib, no server).
- REDIS_URL is a syntactically valid URL; tests do NOT connect to a live Redis
  (readiness/connection are exercised separately and tolerate absence).
"""

from __future__ import annotations

import os

# Must be set before `app.config` is first imported.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-in-prod")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_foundation.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
os.environ.setdefault("BACKEND_CORS_ORIGINS", "http://localhost:3000")
