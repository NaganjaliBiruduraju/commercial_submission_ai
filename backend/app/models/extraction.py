"""
ExtractedField and Evidence ORM models.

ExtractedField: One structured fact extracted from a document.
  Each field has a value (stored as JSON to accommodate different types),
  a confidence score, and an override mechanism for underwriter corrections.

Evidence: The provenance record for an ExtractedField.
  Stores exactly where in which document the value came from.
  The LLM is FORBIDDEN from fabricating evidence records.
  Every evidence record must point to a real document in the database.

Override tracking:
  When an underwriter corrects an extracted value, the original is preserved
  in the ExtractedField record alongside the override. This is critical for
  audit compliance and for improving extraction quality over time.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ExtractedField(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "extracted_fields"

    __table_args__ = (
        Index("ix_extracted_fields_submission_id", "submission_id"),
        Index("ix_extracted_fields_document_id", "document_id"),
        Index("ix_extracted_fields_field_name", "field_name"),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        comment="Source document — null if field was synthesized across documents",
    )

    # -------------------------------------------------------------------------
    # Field identity
    # -------------------------------------------------------------------------
    field_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Canonical field name e.g. annual_revenue, employee_count",
    )
    field_label: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Human-readable label for display",
    )

    # -------------------------------------------------------------------------
    # Value — stored as JSON to handle string, number, list, dict uniformly
    # null means the field was not found in the document (not zero, not empty)
    # -------------------------------------------------------------------------
    field_value: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Extracted value as JSON. null = not present in document",
    )
    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Extraction confidence 0.0–1.0",
    )

    # -------------------------------------------------------------------------
    # Override — human underwriter correction
    # -------------------------------------------------------------------------
    is_overridden: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default="false",
    )
    override_value: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Underwriter-corrected value — original preserved in field_value",
    )
    override_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Required when is_overridden=True — explains why the AI value was incorrect",
    )
    overridden_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    overridden_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    evidence: Mapped[list["Evidence"]] = relationship(
        "Evidence",
        back_populates="extracted_field",
        lazy="noload",
        cascade="all, delete-orphan",
    )

    @property
    def effective_value(self) -> dict | None:
        """Return the override value if set, otherwise the extracted value."""
        return self.override_value if self.is_overridden else self.field_value

    def __repr__(self) -> str:
        return f"<ExtractedField {self.field_name!r} overridden={self.is_overridden}>"


class Evidence(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Provenance record linking an ExtractedField to its source in a document.

    Every AI-derived important fact must have at least one Evidence record.
    The UI navigates from field → evidence → source document page.

    Immutability: Evidence records are never updated after creation.
    If an extraction is re-run, new Evidence records are created and old ones
    are soft-deleted via is_active=False.
    """
    __tablename__ = "evidence"

    __table_args__ = (
        Index("ix_evidence_extracted_field_id", "extracted_field_id"),
        Index("ix_evidence_document_id", "document_id"),
    )

    extracted_field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extracted_fields.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Source location
    # -------------------------------------------------------------------------
    document_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="original_filename of the source document at time of extraction",
    )
    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="1-based page number where the value was found",
    )
    section: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Section heading or table name within the page",
    )
    source_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Exact text from the document that the value was extracted from",
    )
    extraction_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this extraction was performed",
    )
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default="true",
        comment="False when superseded by a re-extraction",
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    extracted_field: Mapped["ExtractedField"] = relationship(
        "ExtractedField",
        back_populates="evidence",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return (
            f"<Evidence doc={self.document_name!r} "
            f"page={self.page_number} field={self.extracted_field_id}>"
        )
