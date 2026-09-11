"""
Submission Pydantic schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.base import InsightBaseModel, TimestampSchema
from app.core.constants import SubmissionStatus
from app.schemas.user import UserSummary


class SubmissionCreate(InsightBaseModel):
    """Request body to create a new submission."""
    broker_name: str | None = Field(default=None, max_length=255)
    broker_email: str | None = Field(default=None, max_length=255)
    broker_company: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class SubmissionUpdate(InsightBaseModel):
    """Partial update — all fields optional."""
    applicant_name: str | None = Field(default=None, max_length=255)
    applicant_business_type: str | None = Field(default=None, max_length=255)
    applicant_industry: str | None = Field(default=None, max_length=255)
    broker_name: str | None = Field(default=None, max_length=255)
    broker_email: str | None = Field(default=None, max_length=255)
    assigned_to: uuid.UUID | None = None


class SubmissionSummary(InsightBaseModel, TimestampSchema):
    """Compact representation for list views / dashboard table."""
    id: uuid.UUID
    submission_number: str
    applicant_name: str | None = None
    broker_name: str | None = None
    broker_company: str | None = None
    status: SubmissionStatus
    assigned_underwriter: UserSummary | None = None
    document_count: int = 0
    has_conflicts: bool = False
    has_missing_info: bool = False
    risk_category: str | None = None
    risk_score: int | None = None


class SubmissionResponse(InsightBaseModel, TimestampSchema):
    """Full submission detail response."""
    id: uuid.UUID
    submission_number: str
    applicant_name: str | None = None
    applicant_business_type: str | None = None
    applicant_industry: str | None = None
    broker_name: str | None = None
    broker_email: str | None = None
    broker_company: str | None = None
    status: SubmissionStatus
    failure_reason: str | None = None
    assigned_to: uuid.UUID | None = None
    assigned_underwriter: UserSummary | None = None
    created_by: uuid.UUID | None = None
    creator: UserSummary | None = None


class SubmissionStatusUpdate(InsightBaseModel):
    """Internal schema for updating submission status through the pipeline."""
    status: SubmissionStatus
    failure_reason: str | None = None
