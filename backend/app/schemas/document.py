"""
Document Pydantic schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.base import InsightBaseModel, TimestampSchema
from app.core.constants import DocumentProcessingStatus, DocumentType


class DocumentResponse(InsightBaseModel, TimestampSchema):
    """Full document detail response."""
    id: uuid.UUID
    submission_id: uuid.UUID
    original_filename: str
    mime_type: str
    file_size_bytes: int
    file_extension: str
    document_type: DocumentType | None = None
    classification_confidence: float | None = None
    classification_reason: str | None = None
    processing_status: DocumentProcessingStatus
    failure_reason: str | None = None
    page_count: int | None = None
    is_scanned: bool | None = None
    version_number: int
    is_current_version: bool
    uploaded_by: uuid.UUID | None = None


class DocumentSummary(InsightBaseModel):
    """Compact document representation for embedding in submission responses."""
    id: uuid.UUID
    original_filename: str
    document_type: DocumentType | None = None
    processing_status: DocumentProcessingStatus
    classification_confidence: float | None = None
    version_number: int
    is_current_version: bool
    file_size_bytes: int


class DocumentVersionResponse(InsightBaseModel, TimestampSchema):
    """Document version history entry."""
    id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    file_size_bytes: int
    checksum_sha256: str | None = None
    uploaded_by: uuid.UUID | None = None
    change_note: str | None = None


class DocumentClassificationResult(InsightBaseModel):
    """Result of the classification pipeline for a single document."""
    document_id: uuid.UUID
    document_type: DocumentType
    confidence: float = Field(ge=0.0, le=1.0)
    classification_reason: str
    alternative_type: DocumentType | None = None
    classified_by: str = Field(
        description="'deterministic' or LLM model name"
    )
