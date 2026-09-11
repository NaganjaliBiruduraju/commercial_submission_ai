"""
Document and DocumentVersion ORM models.

Design decisions:
  - Documents are NEVER silently overwritten. A new upload of the same form
    creates a new DocumentVersion record, preserving the full audit trail.
  - stored_filename uses a UUID — never the original user-provided filename.
    This prevents path traversal attacks and filename collisions.
  - original_filename is stored in the database for display purposes only.
  - document_type is set by the classification pipeline.
  - processing_status tracks the document's individual pipeline progress
    (separate from the submission's overall status).

Relationships:
  Document → Submission (many-to-one)
  Document → DocumentVersions (one-to-many)
  Document → ExtractedFields (one-to-many)
  Document → Evidence (one-to-many)
"""
from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import DocumentProcessingStatus, DocumentType
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "documents"

    __table_args__ = (
        Index("ix_documents_submission_id", "submission_id"),
        Index("ix_documents_document_type", "document_type"),
        Index("ix_documents_processing_status", "processing_status"),
    )

    # -------------------------------------------------------------------------
    # Ownership
    # -------------------------------------------------------------------------
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        comment="Parent submission",
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # -------------------------------------------------------------------------
    # File metadata
    # -------------------------------------------------------------------------
    original_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Original filename as submitted by the broker — display only",
    )
    stored_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        unique=True,
        comment="UUID-based filename on disk — prevents path traversal and collisions",
    )
    mime_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="MIME type validated at upload — determines which parser is used",
    )
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="File size in bytes — validated against MAX_UPLOAD_SIZE_MB",
    )
    file_extension: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Lowercase extension: pdf, docx, xlsx, csv, jpg, jpeg, png",
    )
    checksum_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 hash for integrity verification and duplicate detection",
    )

    # -------------------------------------------------------------------------
    # Classification (populated by Phase 6)
    # -------------------------------------------------------------------------
    document_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        default=None,
        comment="Classified document type — null until classification runs",
    )
    classification_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Classifier confidence 0.0–1.0",
    )
    classification_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Explanation of why this document type was assigned",
    )

    # -------------------------------------------------------------------------
    # Processing state
    # -------------------------------------------------------------------------
    processing_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DocumentProcessingStatus.PENDING,
        server_default=DocumentProcessingStatus.PENDING.value,
    )
    failure_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Set when processing_status=FAILED",
    )
    page_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Total pages — set after parsing",
    )
    is_scanned: Mapped[bool | None] = mapped_column(
        nullable=True,
        comment="True if the document required OCR — set during parsing",
    )

    # -------------------------------------------------------------------------
    # Version tracking
    # -------------------------------------------------------------------------
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="Version number within the submission for this document type",
    )
    is_current_version: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default="true",
        comment="False when a newer version of this document has been uploaded",
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    submission: Mapped["Submission"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Submission",
        back_populates="documents",
        lazy="noload",
    )
    versions: Mapped[list["DocumentVersion"]] = relationship(
        "DocumentVersion",
        back_populates="document",
        lazy="noload",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number",
    )
    uploader: Mapped["User | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User",
        foreign_keys=[uploaded_by],
        lazy="noload",
    )

    def __repr__(self) -> str:
        return (
            f"<Document {self.original_filename!r} "
            f"type={self.document_type!r} v{self.version_number}>"
        )


class DocumentVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Immutable version record for each document upload.

    When a broker re-submits a corrected ACORD form:
    - The existing Document record has is_current_version set to False
    - A new Document record is created with version_number incremented
    - Both DocumentVersion records are preserved
    This ensures the audit trail is never lost.
    """
    __tablename__ = "document_versions"

    __table_args__ = (
        Index("ix_document_versions_document_id", "document_id"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    stored_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="UUID filename of this specific version",
    )
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    change_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional note from the uploader explaining what changed",
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="versions",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<DocumentVersion doc={self.document_id} v{self.version_number}>"
