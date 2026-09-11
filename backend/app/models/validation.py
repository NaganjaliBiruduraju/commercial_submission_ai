"""
ValidationIssue ORM model.

Validation issues are produced by the DETERMINISTIC Python validation engine.
The LLM does NOT generate these records.

Issue types:
  CONFLICT  — Two documents report different values for the same field
              e.g. ACORD revenue $25M vs Financial Statement revenue $30M
  MISSING   — A required field is absent from all documents
  INVALID   — A field present but fails a business rule
              e.g. employee_count = -5
  WARNING   — Non-blocking concern the underwriter should be aware of

Resolution tracking:
  Underwriters can resolve issues with a note explaining why it was
  acceptable or what action was taken. Resolved issues remain in the
  database for audit purposes — they are never deleted.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import ValidationIssueType, ValidationSeverity
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ValidationIssue(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "validation_issues"

    __table_args__ = (
        Index("ix_validation_issues_submission_id", "submission_id"),
        Index("ix_validation_issues_issue_type", "issue_type"),
        Index("ix_validation_issues_is_resolved", "is_resolved"),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Issue classification
    # -------------------------------------------------------------------------
    issue_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="CONFLICT | MISSING | INVALID | WARNING",
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ValidationSeverity.WARNING.value,
        comment="ERROR | WARNING | INFO",
    )

    # -------------------------------------------------------------------------
    # Issue details
    # -------------------------------------------------------------------------
    field_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="The field this issue relates to — null for submission-level issues",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Short one-line description for display in the UI",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Full explanation of the issue and its underwriting impact",
    )
    affected_documents: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment="List of document_ids involved in this issue",
    )
    conflicting_values: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="For CONFLICT issues: {document_id: value} mapping showing each document's value",
    )
    suggested_action: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Recommended action for the underwriter to resolve this issue",
    )

    # -------------------------------------------------------------------------
    # Resolution tracking
    # -------------------------------------------------------------------------
    is_resolved: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default="false",
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Required when resolving — explains how the issue was addressed",
    )

    def __repr__(self) -> str:
        return (
            f"<ValidationIssue {self.issue_type!r} "
            f"field={self.field_name!r} resolved={self.is_resolved}>"
        )
