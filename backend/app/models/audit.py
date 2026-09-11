"""
AuditLog ORM model.

Insurance workflows require a forensic-quality audit trail.
Every important state change creates an immutable AuditLog record.

IMMUTABILITY:
  AuditLog records are NEVER updated or deleted.
  No UPDATE or DELETE operations are permitted on this table.
  This is enforced at the repository layer — the AuditLogRepository
  exposes only an append() method.

What is tracked:
  - Who performed the action (actor_id → users.id)
  - What entity was changed (entity_type + entity_id)
  - What the value was before (old_value JSON)
  - What the value is after (new_value JSON)
  - When it happened (created_at — server-side timestamp)
  - Why it happened (reason — required for overrides and decisions)
  - From where (ip_address — for security auditing)

Examples of audited actions:
  - User login / logout
  - Document uploaded
  - Submission status changed
  - Extracted field overridden by underwriter
  - Validation issue resolved
  - Knowledge document approved
  - Underwriter decision recorded
  - User role changed
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import AuditAction
from app.models.base import Base, UUIDPrimaryKeyMixin
from sqlalchemy import DateTime, func
from datetime import datetime


class AuditLog(Base, UUIDPrimaryKeyMixin):
    """
    Immutable audit log entry.

    Note: deliberately NOT using TimestampMixin because:
      - created_at is the only timestamp needed (no updated_at)
      - server_default=func.now() ensures the DB sets it, not the app
        (more reliable for forensic purposes)
    """
    __tablename__ = "audit_logs"

    __table_args__ = (
        Index("ix_audit_logs_actor_id", "actor_id"),
        Index("ix_audit_logs_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    # -------------------------------------------------------------------------
    # Timestamp — server-set for forensic integrity
    # -------------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Action
    # -------------------------------------------------------------------------
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="AuditAction enum value",
    )

    # -------------------------------------------------------------------------
    # Entity
    # -------------------------------------------------------------------------
    entity_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="e.g. submission, document, extracted_field, user, knowledge_document",
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="UUID of the entity that was changed",
    )

    # -------------------------------------------------------------------------
    # Actor
    # -------------------------------------------------------------------------
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Null for system-generated actions",
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="IPv4 or IPv6 address — 45 chars covers IPv6",
    )

    # -------------------------------------------------------------------------
    # Change record
    # -------------------------------------------------------------------------
    old_value: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="State before the change — null for CREATED actions",
    )
    new_value: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="State after the change — null for DELETED actions",
    )
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Required for OVERRIDDEN and decision actions — human explanation",
    )

    # -------------------------------------------------------------------------
    # Context
    # -------------------------------------------------------------------------
    submission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Denormalized for fast submission-level audit log queries",
    )
    request_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="HTTP request ID for correlating with application logs",
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    actor: Mapped["User | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User",
        foreign_keys=[actor_id],
        lazy="noload",
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog action={self.action!r} "
            f"entity={self.entity_type}/{self.entity_id}>"
        )
