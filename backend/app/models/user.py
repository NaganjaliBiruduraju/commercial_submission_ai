"""
User and Role ORM models.

Design decisions:
  - Role is a separate table (not an enum column) so that permissions can be
    extended in the future without schema migrations.
  - hashed_password stores only the bcrypt hash — never the plaintext.
  - is_active allows soft-disabling a user without deleting their audit history.
  - last_login is informational — not used for security decisions.
  - email is case-insensitively unique (indexed as lowercase).

Relationship:
  User → Role (many-to-one): one user has one role
  Role → Users (one-to-many): one role has many users
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Role(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    RBAC role definition.

    Seeded at startup: ADMIN, UNDERWRITER, REVIEWER.
    Additional roles can be added without schema changes.
    """
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        comment="Role name: ADMIN, UNDERWRITER, REVIEWER",
    )
    description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="role",
        lazy="noload",  # always explicit — never auto-loaded
    )

    def __repr__(self) -> str:
        return f"<Role name={self.name!r}>"


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Application user.

    SECURITY RULES:
    - hashed_password is NEVER returned in API responses
    - Passwords are hashed with bcrypt (see app.core.security)
    - Email is stored lowercase for case-insensitive comparison
    - is_active=False prevents login without deleting the user record
    """
    __tablename__ = "users"

    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Work email — stored lowercase, used as login identifier",
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="bcrypt hash — NEVER store or return plaintext passwords",
    )
    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Soft disable — inactive users cannot log in",
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful login timestamp — informational only",
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    role: Mapped["Role"] = relationship(
        "Role",
        back_populates="users",
        lazy="joined",  # always load role with user — needed for every auth check
    )

    def __repr__(self) -> str:
        return f"<User email={self.email!r} role={self.role_id}>"
