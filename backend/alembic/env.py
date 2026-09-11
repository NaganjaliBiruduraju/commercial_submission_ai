"""
Alembic environment configuration.

Supports both:
  - Offline mode: generate SQL without connecting to the database
  - Online mode (async): connect to PostgreSQL and apply migrations

We use the async engine from app.database.session so that Alembic uses
the same connection settings as the application.

To run migrations:
    cd backend
    alembic upgrade head          # apply all pending migrations
    alembic revision --autogenerate -m "describe change"  # generate new migration
    alembic downgrade -1          # roll back one migration
"""
from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Make sure backend/app is importable when running alembic from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import all models so Alembic's autogenerate can detect them
from app.database.base import Base  # noqa: E402  (triggers all model imports)
from app.core.config import get_settings  # noqa: E402

# Alembic Config object — gives access to values in alembic.ini
config = context.config

# Configure Python logging from alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata Alembic uses to compare against the live DB for autogenerate
target_metadata = Base.metadata

# Override the sqlalchemy.url from alembic.ini with the value from
# our settings (which reads from .env) so we never hard-code credentials.
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    """
    Run migrations in "offline" mode.

    Generates SQL without an actual DB connection.
    Useful for reviewing migrations before applying them
    or for CI environments where the DB is not available.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Include schema-level comparisons
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using the async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # don't pool connections during migrations
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in "online" mode (actually connects to the DB)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
