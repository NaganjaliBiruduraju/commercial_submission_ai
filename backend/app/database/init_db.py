"""
Database initialization and first-run setup.

This module handles:
  1. Creating the pgvector extension (required for embedding similarity search)
  2. Creating all tables from SQLAlchemy metadata (development only)
  3. Seeding the database with required initial data:
     - Default roles (ADMIN, UNDERWRITER, REVIEWER)
     - Default ADMIN user (credentials from environment — never hard-coded)

In production, schema changes are managed through Alembic migrations.
The create_tables() function should only be called in development/testing.

Why seed roles and an admin user?
  The application cannot function without roles.
  The first admin user must be created before anyone can log in.
  We read the initial admin credentials from environment variables so
  they are never hard-coded in source code.
"""
from __future__ import annotations

import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database.session import engine, DatabaseSession

logger = get_logger(__name__)


async def create_pgvector_extension() -> None:
    """
    Create the pgvector extension if it does not already exist.

    pgvector enables vector similarity search in PostgreSQL.
    It is used by the RAG subsystem to find semantically similar
    knowledge chunks for a given query.

    This requires the pgvector extension to be installed in PostgreSQL.
    Install with: CREATE EXTENSION IF NOT EXISTS vector;
    Or via apt: apt-get install postgresql-16-pgvector
    """
    async with engine.begin() as conn:
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            logger.info("pgvector extension ready")
        except Exception as e:
            # Non-fatal in Phase 1 — pgvector is needed for Phase 13 (Vector DB)
            logger.warning(
                "Could not create pgvector extension — RAG will not work until "
                "pgvector is installed in PostgreSQL",
                extra={"error_type": type(e).__name__},
            )


async def create_tables() -> None:
    """
    Create all database tables from SQLAlchemy metadata.

    DEVELOPMENT AND TESTING ONLY.
    In production, use: alembic upgrade head

    This function is idempotent — safe to call multiple times.
    It uses CREATE TABLE IF NOT EXISTS internally.
    """
    # Import Base here to trigger model registration
    from app.database.base import Base  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created (development mode)")


async def seed_roles(db: AsyncSession) -> None:
    """
    Ensure all required roles exist in the database.

    Roles are upserted by name — safe to call on every startup.
    Does not modify description of existing roles so manual edits are preserved.
    """
    from sqlalchemy import select
    from app.models.user import Role
    from app.core.constants import UserRole

    role_definitions = {
        UserRole.ADMIN: "Full system access — manage users, knowledge base, and configuration",
        UserRole.UNDERWRITER: "Review submissions, override extractions, and record decisions",
        UserRole.REVIEWER: "Read-only access to submissions and reports",
    }

    for role_enum, description in role_definitions.items():
        result = await db.execute(
            select(Role).where(Role.name == role_enum.value)
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            db.add(Role(name=role_enum.value, description=description))
            logger.info(f"Seeded role: {role_enum.value}")

    await db.commit()
    logger.info("Role seeding complete")


async def seed_admin_user(db: AsyncSession) -> None:
    """
    Create the initial admin user if no admin users exist.

    Admin credentials are read from environment variables:
      INITIAL_ADMIN_EMAIL    — default admin email
      INITIAL_ADMIN_PASSWORD — default admin password (must be changed after first login)

    IMPORTANT: These variables must be set in .env before first startup.
    The password is hashed with bcrypt before storage.
    The plaintext password is NEVER stored or logged.
    """
    from sqlalchemy import select
    from app.models.user import Role, User
    from app.core.security import hash_password
    from app.core.constants import UserRole

    admin_email = os.getenv("INITIAL_ADMIN_EMAIL", "admin@insightai.local")
    admin_password = os.getenv("INITIAL_ADMIN_PASSWORD", "")

    if not admin_password:
        logger.warning(
            "INITIAL_ADMIN_PASSWORD not set — skipping admin user seed. "
            "Set this environment variable before first startup."
        )
        return

    # Check if any admin already exists
    admin_role_result = await db.execute(
        select(Role).where(Role.name == UserRole.ADMIN.value)
    )
    admin_role = admin_role_result.scalar_one_or_none()
    if admin_role is None:
        logger.error("Admin role not found — run seed_roles() first")
        return

    existing_result = await db.execute(
        select(User).where(User.email == admin_email.lower().strip())
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        logger.info(f"Admin user already exists — skipping seed: {admin_email}")
        return

    admin_user = User(
        email=admin_email.lower().strip(),
        hashed_password=hash_password(admin_password),
        full_name="System Administrator",
        role_id=admin_role.id,
        is_active=True,
    )
    db.add(admin_user)
    await db.commit()
    logger.info(f"Admin user seeded: {admin_email}")
    # Plaintext password is NOT logged — only the email


async def initialize_database() -> None:
    """
    Full database initialization sequence.

    Called once at application startup from main.py lifespan handler.
    Order matters:
      1. pgvector extension (needed before any vector columns are created)
      2. Tables (only in development)
      3. Seed data (roles and admin user)
    """
    logger.info("Initializing database...")

    await create_pgvector_extension()

    # In development, auto-create tables for convenience
    # In production, this step is skipped — migrations handle schema
    app_env = os.getenv("APP_ENV", "development")
    if app_env == "development":
        await create_tables()

    async with DatabaseSession() as db:
        await seed_roles(db)
        await seed_admin_user(db)

    logger.info("Database initialization complete")


async def check_database_connection() -> bool:
    """
    Verify the database is reachable.

    Called from the health check endpoint and at startup.
    Returns True if connected, False otherwise.
    Does NOT raise — callers check the return value.
    """
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(
            "Database connection check failed",
            extra={"error_type": type(e).__name__},
        )
        return False
