"""Redis connection layer.

The client is built from ``REDIS_URL`` (from .env only) and created lazily so
importing this module never forces a connection.
"""

from __future__ import annotations

import redis

from app.config import settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Return a lazily-created Redis client built from REDIS_URL."""
    global _client
    if _client is None:
        if not settings.REDIS_URL:
            raise RuntimeError(
                "REDIS_URL is not configured. Set it in your .env "
                "(see backend/.env.example)."
            )
        _client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


def check_connection() -> bool:
    """Ping Redis. Used by the readiness probe."""
    return bool(get_redis().ping())
