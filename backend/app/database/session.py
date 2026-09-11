"""
Async SQLAlchemy session management.

Architecture decisions:
  - asyncpg driver:  Native async PostgreSQL driver — required for FastAPI's
                     async route handlers. Avoids blocking the event loop.
  - AsyncEngine:     Single engine per application process, created at startup.
  - AsyncSessionLocal: Session factory — each call creates a new session.
  - get_db():        FastAPI dependency. Yields one session per HTTP request,
                     commits on success, rolls back on exception, always closes.

Connection pooling is configured via settings:
  pool_size:    Number of persistent connections kept open
  max_overflow: Extra connections allowed above pool_size under load
  pool_timeout: Seconds to wait for a free connection before raising

Why async?
  FastAPI is built on async/await. If we used a synchronous database driver,
  every database call would block the event loop, eliminating the concurrency
  benefit. asyncpg releases the event loop between queries.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Engine — created once at module import time
# ---------------------------------------------------------------------------
# echo=False in all environments — SQL statements are verbose and would
# pollute structured logs. Enable temporarily for debugging only.
# pool_pre_ping=True: validate connections before use, silently reconnecting
# if the database server restarted (important for long-running services).

def _create_engine() -> AsyncEngine:
    """
    Create the async SQLAlchemy engine from configuration.

    Separated into a function so it can be called lazily in tests,
    where DATABASE_URL may be a test database.
    """
    engine_kwargs: dict[str, Any] = {
        "echo": False,
        "pool_pre_ping": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        # Return connections to the pool promptly
        "pool_recycle": 1800,  # 30 minutes
    }

    return create_async_engine(settings.database_url, **engine_kwargs)


engine: AsyncEngine = _create_engine()

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
# expire_on_commit=False: After commit, SQLAlchemy normally expires all
# attributes, requiring a second SELECT to read them. Setting False avoids
# this extra query — we read all data before committing in our services.
# autoflush=False: We flush explicitly when needed, not on every query.

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a database session per request.

    Usage in route handlers:
        @router.get("/submissions")
        async def list_submissions(db: AsyncSession = Depends(get_db)):
            ...

    Or using the type alias from api/deps.py:
        async def list_submissions(db: DatabaseDep):
            ...

    Guarantees:
    - One session per request
    - Commits automatically on success
    - Rolls back automatically on any exception
    - Session is always closed, even if an exception occurred
    - Never leaks connections back to the pool in a bad state
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Session context manager for use outside FastAPI (e.g., background tasks)
# ---------------------------------------------------------------------------

class DatabaseSession:
    """
    Async context manager for database sessions outside the request/response cycle.

    Use this in background tasks, CLI scripts, and Alembic operations
    where FastAPI's Depends() is not available.

    Usage:
        async with DatabaseSession() as db:
            result = await db.execute(select(User))

    Like get_db(), it commits on success and rolls back on exception.
    """

    async def __aenter__(self) -> AsyncSession:
        self._session = AsyncSessionLocal()
        return self._session

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: Exception | None,
        exc_tb: object | None,
    ) -> bool:
        try:
            if exc_val is None:
                await self._session.commit()
            else:
                await self._session.rollback()
        finally:
            await self._session.close()
        return False  # Do not suppress exceptions
