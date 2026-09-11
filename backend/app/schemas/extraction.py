"""
Extraction and Evidence Pydantic schemas.

The evidence schema is central to the system's explainability.
Every extracted field must reference the exact source in the document.
The LLM is FORBIDDEN from fabricating evidence references.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.schemas.base import InsightBaseModel, TimestampSchema


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

class EvidenceResponse(InsightBaseModel, TimestampSchema):
    """Source provenance for an extracted field."""
    id: uuid.UUID
    extracted_field_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    page_number: int | None = None
    section: str | None = None
    source_text: str | None = None
    extraction_timestamp: datetime | None = None
    is_active: bool


class EvidenceCreate(InsightBaseModel):
    """Internal schema for creating an Evidence record during extraction."""
    document_id: uuid.UUID
    document_name: str
    page_number: int | None = None
    section: str | None = None
    source_text: str | None = None
    extraction_timestamp: datetime | None = None


# ---------------------------------------------------------------------------
# Extracted Field
# ---------------------------------------------------------------------------

class ExtractedFieldResponse(InsightBaseModel, TimestampSchema):
    """
    A single extracted fact with its evidence chain.

    effective_value returns override_value if overridden, else field_value.
    The UI shows effective_value but allows viewing the original field_value
    to understand what the AI extracted before correction.
    """
    id: uuid.UUID
    submission_id: uuid.UUID
    document_id: uuid.UUID | None = None
    field_name: str
    field_label: str | None = None
    field_value: Any = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_overridden: bool
    override_value: Any = None
    override_reason: str | None = None
    overridden_by: uuid.UUID | None = None
    overridden_at: datetime | None = None
    effective_value: Any = None
    evidence: list[EvidenceResponse] = Field(default_factory=list)


class ExtractedFieldOverride(InsightBaseModel):
    """
    Request body for an underwriter to override an extracted value.

    override_reason is required — underwriters must explain why
    the AI extraction was incorrect. This is critical for audit compliance
    and for identifying systematic extraction failures.
    """
    override_value: Any = Field(description="The correct value per the underwriter")
    override_reason: str = Field(
        min_length=10,
        description="Required: explain why the AI value was incorrect",
    )


# ---------------------------------------------------------------------------
# Full submission extraction result
# ---------------------------------------------------------------------------

class SubmissionExtractionSchema(InsightBaseModel):
    """
    Structured extraction result for a complete submission.

    This is the primary output of the extraction pipeline.
    null values mean the information was NOT found in the documents.
    The LLM MUST return null — never a guess — for missing fields.
    """
    submission_id: uuid.UUID

    # Applicant
    company_name: str | None = None
    dba_name: str | None = None
    business_type: str | None = None
    industry: str | None = None
    years_in_business: int | None = None
    business_operations: str | None = None

    # Financials
    annual_revenue: float | None = Field(
        default=None,
        description="Annual revenue in USD. null if not stated in documents.",
    )
    employee_count: int | None = Field(
        default=None,
        ge=0,
        description="Total employee count. null if not stated.",
    )
    location_count: int | None = Field(
        default=None,
        ge=0,
        description="Number of business locations. null if not stated.",
    )

    # Coverage request
    requested_coverages: list[str] = Field(default_factory=list)
    effective_date: str | None = Field(
        default=None,
        description="ISO 8601 date string. null if not stated.",
    )
    expiration_date: str | None = Field(
        default=None,
        description="ISO 8601 date string. null if not stated.",
    )

    # Contact
    primary_contact_name: str | None = None
    primary_contact_email: str | None = None
    primary_contact_phone: str | None = None
    mailing_address: str | None = None

    # Metadata
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Fields that are required but were not found",
    )
    extraction_notes: str | None = Field(
        default=None,
        description="Any notable issues or ambiguities encountered during extraction",
    )
    extracted_fields: list[ExtractedFieldResponse] = Field(default_factory=list)
