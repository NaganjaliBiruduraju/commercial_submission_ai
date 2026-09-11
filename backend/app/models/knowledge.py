"""
KnowledgeDocument and KnowledgeChunk ORM models.

KnowledgeDocument: An admin-approved underwriting guideline or policy document.
  ONLY documents with status=ACTIVE and within their effective date window
  are retrieved for RAG. Expired and archived documents are retained for
  audit but excluded from retrieval.

KnowledgeChunk: A text chunk from a KnowledgeDocument, stored with its
  embedding vector for similarity search.

  Why chunking?
    LLMs have limited context windows. A full underwriting guideline may be
    50+ pages. We split it into overlapping chunks (~500 tokens, 50-token
    overlap) so the most relevant sections are retrieved, not the full doc.

  pgvector:
    The embedding column uses the pgvector extension for PostgreSQL.
    Similarity search uses cosine distance (L2 normalized embeddings).
    This enables "find the most semantically similar guideline sections
    for this submission's industry and coverage type."

IMPORTANT:
  Submission documents uploaded by brokers are NEVER stored here.
  Only admin-uploaded and admin-approved knowledge is indexed.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import KnowledgeDocumentStatus
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class KnowledgeDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "knowledge_documents"

    __table_args__ = (
        Index("ix_knowledge_documents_status", "status"),
        Index("ix_knowledge_documents_category", "category"),
    )

    # -------------------------------------------------------------------------
    # Document metadata
    # -------------------------------------------------------------------------
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="e.g. UNDERWRITING_GUIDELINE, COVERAGE_RULE, RISK_APPETITE, FAQ",
    )
    version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Document version e.g. 1.0, 2.3",
    )
    effective_date: Mapped[str | None] = mapped_column(
        Date,
        nullable=True,
        comment="Date from which this document is authoritative",
    )
    expiration_date: Mapped[str | None] = mapped_column(
        Date,
        nullable=True,
        comment="Date after which this document should not be used for RAG",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=KnowledgeDocumentStatus.DRAFT.value,
        server_default=KnowledgeDocumentStatus.DRAFT.value,
        comment="DRAFT | PENDING_APPROVAL | ACTIVE | EXPIRED | ARCHIVED",
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Admin user who approved this document for RAG use",
    )

    # -------------------------------------------------------------------------
    # File
    # -------------------------------------------------------------------------
    stored_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        unique=True,
        comment="UUID-based stored filename",
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(nullable=True)

    # -------------------------------------------------------------------------
    # Indexing state
    # -------------------------------------------------------------------------
    is_indexed: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default="false",
        comment="True once chunks and embeddings have been generated",
    )
    chunk_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Number of chunks generated from this document",
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        "KnowledgeChunk",
        back_populates="document",
        lazy="noload",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<KnowledgeDocument {self.title!r} status={self.status!r}>"


class KnowledgeChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A text chunk from a KnowledgeDocument with its embedding vector.

    The embedding column is declared as JSON here in Phase 1 (no pgvector yet).
    Phase 13 (Vector Database) will migrate this to the native pgvector type:
      from pgvector.sqlalchemy import Vector
      embedding: Mapped[list[float]] = mapped_column(Vector(384))

    This two-phase approach avoids a hard pgvector dependency in Phase 1
    while keeping the schema structure correct.
    """
    __tablename__ = "knowledge_chunks"

    __table_args__ = (
        Index("ix_knowledge_chunks_document_id", "document_id"),
        Index("ix_knowledge_chunks_chunk_index", "chunk_index"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Chunk content
    # -------------------------------------------------------------------------
    chunk_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The text content of this chunk (~500 tokens)",
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="0-based sequential index within the document",
    )
    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Page where this chunk starts",
    )
    section: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Section heading for citation purposes",
    )

    # -------------------------------------------------------------------------
    # Embedding vector
    # Phase 1: stored as JSON (list of floats)
    # Phase 13: migrated to pgvector Vector(384) column
    # -------------------------------------------------------------------------
    embedding: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Embedding vector — JSON in Phase 1, pgvector in Phase 13",
    )
    embedding_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Model used to generate this embedding — tracked for reproducibility",
    )

    # -------------------------------------------------------------------------
    # Source metadata (denormalized for retrieval performance)
    # -------------------------------------------------------------------------
    chunk_metadata: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Retained source metadata: title, category, version, effective_date",
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    document: Mapped["KnowledgeDocument"] = relationship(
        "KnowledgeDocument",
        back_populates="chunks",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return (
            f"<KnowledgeChunk doc={self.document_id} "
            f"idx={self.chunk_index} page={self.page_number}>"
        )
