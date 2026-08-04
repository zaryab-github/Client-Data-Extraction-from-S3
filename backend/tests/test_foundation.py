"""Lightweight Phase 1 foundation tests.

These verify wiring only — no business logic:
  * Environment configuration loads.
  * Database configuration loads (engine builds; SELECT 1 works on SQLite).
  * Redis configuration loads (client builds from URL).
  * Celery configuration loads (broker/backend set from config).
  * Backend starts (FastAPI app builds; /health and / respond).
"""

from __future__ import annotations


def test_environment_configuration_loads():
    from app.config import settings

    assert settings.APP_NAME
    assert settings.API_V1_PREFIX == "/api/v1"
    assert settings.DATABASE_URL          # provided by conftest
    assert settings.REDIS_URL             # provided by conftest
    assert settings.cors_origins == ["http://localhost:3000"]
    # Required-config validation passes with the test env.
    settings.require()


def test_database_configuration_loads():
    from app.db import session as db_layer

    engine = db_layer.get_engine()
    assert engine is not None
    assert str(engine.url).startswith("sqlite")
    # SQLite is serverless, so we can actually run the readiness query.
    assert db_layer.check_connection() is True


def test_redis_configuration_loads():
    from app.config import settings
    from app.core import redis as redis_layer

    client = redis_layer.get_redis()
    assert client is not None
    # Connection params are derived from REDIS_URL (no live server required here).
    kwargs = client.connection_pool.connection_kwargs
    assert kwargs.get("host")
    assert settings.REDIS_URL.startswith("redis://")


def test_celery_configuration_loads():
    from app.config import settings
    from app.workers.celery_app import celery_app

    assert celery_app.conf.broker_url == settings.celery_broker
    assert celery_app.conf.result_backend == settings.celery_backend
    assert celery_app.conf.timezone == "UTC"


def test_backend_starts():
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.main import app

    with TestClient(app) as client:
        # Root
        r = client.get("/")
        assert r.status_code == 200
        assert r.json()["name"] == settings.APP_NAME

        # Liveness under the versioned prefix
        r = client.get(f"{settings.API_V1_PREFIX}/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
