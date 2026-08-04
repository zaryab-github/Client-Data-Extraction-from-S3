"""Alembic migration environment.

Reads the database URL from application settings (.env), and uses the app's
declarative metadata (all models) as the autogenerate target.

Note: the URL is passed straight to SQLAlchemy (never through Alembic's
ConfigParser), so passwords containing '%' (e.g. URL-encoded '%40' for '@') do
not trigger interpolation errors.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import settings
from app.db.base import Base

# Import models so they register on Base.metadata.
import app.db.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Build the engine directly from settings — bypasses ConfigParser entirely.
    connectable = create_engine(
        settings.DATABASE_URL, poolclass=pool.NullPool, future=True
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
