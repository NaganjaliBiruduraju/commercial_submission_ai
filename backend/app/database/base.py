"""
SQLAlchemy declarative base re-export for the database package.

Alembic's env.py imports Base from this module so it can discover
all registered ORM models for autogenerate.

All ORM models must:
  1. Inherit from Base (defined in app.models.base)
  2. Be imported somewhere before Alembic runs autogenerate
  3. That import chain is: alembic/env.py → app.database.base → app.models → all model files

This indirection keeps app.models.base clean (pure model definitions)
while giving the database package and Alembic a single import target.
"""
from __future__ import annotations

# Re-export Base so Alembic env.py can do: from app.database.base import Base
from app.models.base import Base  # noqa: F401

# Import all models so SQLAlchemy registers them with Base.metadata
# This is the critical step — without these imports, Alembic autogenerate
# will not detect the tables and will generate empty migrations.
import app.models  # noqa: F401  — triggers __init__.py which imports all models
