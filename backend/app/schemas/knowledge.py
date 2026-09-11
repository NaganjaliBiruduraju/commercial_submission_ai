"""
Knowledge base Pydantic schemas.

Knowledge documents are admin-uploaded and admin-approved underwriting guidelines.
Only ACTIVE documents within their effective date window are used for RAG.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import Field

from app.schemas.base import InsightBaseModel, TimestampSchema
from app.core.constants import KnowledgeDocumentStatus


class KnowledgeDocumentCreate(InsightBaseModel):
    """Request body for uploading a new knowledge document (admin only)."""
    title: str = Field(min_length=1, max_length=500)
    category: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=50)
    effective_date: date | None = None
    expiration_date: date | None = None
    description: str | None = None


class KnowledgeDocumentUpdate(InsightBaseModel):
    """Partial update for knowledge document metadata."""
    title: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=100)
    version: str | None = Field(default=None, max_length=50)
    effective_date: date | None = None
    expiration_date: date | None = None
    description: str | None = None


class KnowledgeDocumentResponse(InsightBaseModel, TimestampSchema):
    """Full knowledge document response."""
    id: uuid.UUID
    title: str
    category: str
    version: str
    effective_date: date | None = None
    expiration_date: date | None = None
    description: str | None = None
    status: KnowledgeDocumentStatus
    original_filename: str
    file_size_bytes: int | None = None
    is_indexed: bool
    chunk_count: int | None = None
    uploaded_by: uuid.UUID | None = None
    approved_by: uuid.UUID | None = None


class KnowledgeChunkResponse(InsightBaseModel, TimestampSchema):
    """A single retrieved knowledge chunk with its source metadata."""
    id: uuid.UUID
    document_id: uuid.UUID
    chunk_text: str
    chunk_index: int
    page_number: int | None = None
    section: str | None = None
    embedding_model: str | None = None
    chunk_metadata: dict | None = None

    # Retrieval metadata — added when returned from similarity search
    similarity_score: float | None = Field(
        default=None,
        description="Cosine similarity score 0.0–1.0 from vector search",
    )


class RAGContext(InsightBaseModel):
    """
    Assembled RAG context ready for injection into an LLM prompt.

    Each chunk retains full source metadata so the LLM response can cite
    which guideline influenced its recommendation.
    """
    query: str
    retrieved_chunks: list[KnowledgeChunkResponse] = Field(default_factory=list)
    total_chunks: int = 0
    retrieval_model: str | None = None
