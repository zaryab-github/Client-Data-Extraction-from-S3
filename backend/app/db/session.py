"""Database connection layer.

The engine and session factory are built from ``DATABASE_URL`` (from .env only).
No connection URL is hardcoded. The engine is created lazily so importing this
module never forces a connection or requires the variable to be present.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def _make_engine(url: str) -> Engine:
    # SQLite (used in local/dev/test) needs a special connect arg for threads.
    is_sqlite = url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    engine = create_engine(
        url, pool_pre_ping=True, future=True, connect_args=connect_args
    )
    if is_sqlite:
        # WAL + a busy timeout let concurrent sessions (e.g. an API session and a
        # Celery-eager task session in tests) read/write without long lock stalls.
        # Production uses PostgreSQL, where this is a no-op.
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _record):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()

    return engine


def get_engine() -> Engine:
    """Return a lazily-created SQLAlchemy engine built from DATABASE_URL."""
    global _engine, _SessionFactory
    if _engine is None:
        if not settings.DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is not configured. Set it in your .env "
                "(see backend/.env.example)."
            )
        _engine = _make_engine(settings.DATABASE_URL)
        _SessionFactory = sessionmaker(
            bind=_engine, autoflush=False, autocommit=False, future=True
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the session factory, creating the engine if needed."""
    if _SessionFactory is None:
        get_engine()
    assert _SessionFactory is not None
    return _SessionFactory


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yield a database session and close it afterwards."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def check_connection() -> bool:
    """Open a connection and run ``SELECT 1``. Used by the readiness probe."""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
