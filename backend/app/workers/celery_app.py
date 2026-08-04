"""Celery application.

Broker and result backend come from .env (``CELERY_BROKER_URL`` /
``CELERY_RESULT_BACKEND``, falling back to ``REDIS_URL``). No URLs are hardcoded.
No tasks are defined in Phase 1 — only the configured app instance.
"""

from __future__ import annotations

from celery import Celery

from app.config import settings


def create_celery() -> Celery:
    app = Celery(settings.APP_NAME)
    app.conf.update(
        broker_url=settings.celery_broker,
        result_backend=settings.celery_backend,
        task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
        task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
        worker_concurrency=settings.CELERY_WORKER_CONCURRENCY,
        task_acks_late=True,               # safer for long-running extraction jobs
        worker_prefetch_multiplier=1,      # fair dispatch for uneven, heavy tasks
        task_track_started=True,
        timezone="UTC",
        enable_utc=True,
        # Task queues are declared in later phases (extraction/email/maintenance).
    )
    return app


celery_app = create_celery()
