"""
SQLAlchemy declarative base and shared mixins.

All ORM models inherit from Base plus the relevant mixins.
This enforces a consistent structure across every table:
  - UUID primary keys (PostgreSQL native UUID type — efficient storage and indexing)
  - created_at / updated_at timestamps with timezone awareness
  - created_by for user attribution on mutable records

Using SQLAlchemy 2.0 style: Mapped[] annotations + mapped_column()
This gives full IDE type-checking on model attributes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models."""
    pass


class UUIDPrimaryKeyMixin:
    """UUID primary key using PostgreSQL native UUID type."""
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )


class TimestampMixin:
    """
    Adds created_at and updated_at to every model.

    server_default=func.now() means the database sets the value on INSERT,
    which is more reliable than application-level defaults.
    onupdate is also set at the application level for compatibility.
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class CreatedByMixin:
    """
    Adds created_by (FK to users.id) for audit attribution.
    Nullable=True to allow system-generated records where no user is the actor.
    """
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
