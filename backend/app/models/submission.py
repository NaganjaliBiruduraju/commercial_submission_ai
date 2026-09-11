"""
Submission ORM model.

A Submission represents one complete commercial insurance submission
from a broker. It is the root aggregate — all documents, extractions,
validations, risk assessments, and decisions belong to a submission.

Design decisions:
  - submission_number is a human-readable identifier (e.g. SUB-2025-001234)
    separate from the UUID primary key. Displayed in the UI.
  - status tracks where the submission is in the processing pipeline.
  - assigned_to links to the underwriter responsible for this submission.
  - broker_* fields capture broker contact info denormalized here for
    quick access — the primary source is the broker email document.

Relationships:
  Submission → Documents (one-to-many)
  Submission → ExtractedFields (one-to-many)
  Submission → ValidationIssues (one-to-many)
  Submission → RiskAssessment (one-to-one)
  Submission → UnderwriterDecision (one-to-one)
  Submission → AuditLogs (one-to-many)
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import SubmissionStatus
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Submission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "submissions"

    __table_args__ = (
        Index("ix_submissions_status", "status"),
        Index("ix_submissions_assigned_to", "assigned_to"),
        Index("ix_submissions_created_by", "created_by"),
    )

    # -------------------------------------------------------------------------
    # Core identifiers
    # -------------------------------------------------------------------------
    submission_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        comment="Human-readable identifier e.g. SUB-2025-001234",
    )

    # -------------------------------------------------------------------------
    # Applicant information (denormalized from extraction for quick display)
    # These are populated after extraction — null until then.
    # -------------------------------------------------------------------------
    applicant_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Populated from extraction — null until documents are processed",
    )
    applicant_business_type: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    applicant_industry: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    # -------------------------------------------------------------------------
    # Broker information
    # -------------------------------------------------------------------------
    broker_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    broker_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    broker_company: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # -------------------------------------------------------------------------
    # Processing state
    # -------------------------------------------------------------------------
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=SubmissionStatus.UPLOADED,
        server_default=SubmissionStatus.UPLOADED.value,
        comment="Current pipeline processing state",
    )
    failure_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Set when status=FAILED — human-readable reason for the failure",
    )

    # -------------------------------------------------------------------------
    # Assignment
    # -------------------------------------------------------------------------
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Underwriter assigned to review this submission",
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who created/uploaded this submission",
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    documents: Mapped[list["Document"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Document",
        back_populates="submission",
        lazy="noload",
        cascade="all, delete-orphan",
    )
    assigned_underwriter: Mapped["User | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User",
        foreign_keys=[assigned_to],
        lazy="noload",
    )
    creator: Mapped["User | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User",
        foreign_keys=[created_by],
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Submission {self.submission_number!r} status={self.status!r}>"
