"""Celery application.

Broker and result backend come from .env (``CELERY_BROKER_URL`` /
``CELERY_RESULT_BACKEND``, falling back to ``REDIS_URL``). No URLs are hardcoded.

Task modules are imported via ``include`` so the worker registers them; Celery beat
schedules the retention cleanup.
"""

from __future__ import annotations

from celery import Celery

from app.config import settings

TASK_MODULES = [
    "app.workers.tasks.extraction_task",
    "app.workers.tasks.retention_task",
    "app.workers.tasks.email_task",
]


def create_celery() -> Celery:
    app = Celery(settings.APP_NAME, include=TASK_MODULES)
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
        beat_schedule={
            "retention-cleanup": {
                "task": "run_retention",
                "schedule": float(settings.RETENTION_CLEANUP_INTERVAL_SECONDS),
            },
        },
    )
    return app


celery_app = create_celery()

# Import task modules so tasks are registered whenever celery_app is imported
# (not only inside a worker). Placed at the bottom to avoid a circular import.
from app.workers.tasks import email_task, extraction_task, retention_task  # noqa: E402,F401
