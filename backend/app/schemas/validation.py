"""
Validation issue Pydantic schemas.

Validation issues are produced by deterministic Python rules — not the LLM.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.base import InsightBaseModel, TimestampSchema
from app.core.constants import ValidationIssueType, ValidationSeverity


class ValidationIssueResponse(TimestampSchema, InsightBaseModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    issue_type: ValidationIssueType
    severity: ValidationSeverity
    field_name: str | None = None
    title: str
    description: str
    affected_documents: list[str] = Field(default_factory=list)
    conflicting_values: dict | None = None
    suggested_action: str | None = None
    is_resolved: bool
    resolved_by: uuid.UUID | None = None
    resolved_at: datetime | None = None
    resolution_note: str | None = None


class ValidationIssueSummary(InsightBaseModel):
    """Compact representation for dashboard counts."""
    id: uuid.UUID
    issue_type: ValidationIssueType
    severity: ValidationSeverity
    title: str
    field_name: str | None = None
    is_resolved: bool


class ValidationIssueResolve(InsightBaseModel):
    """Request body for an underwriter to resolve a validation issue."""
    resolution_note: str = Field(
        min_length=10,
        description="Required: explain how this issue was addressed or why it is acceptable",
    )


class ValidationSummary(InsightBaseModel):
    """Aggregate validation result for a submission."""
    submission_id: uuid.UUID
    total_issues: int
    error_count: int
    warning_count: int
    info_count: int
    unresolved_count: int
    conflict_count: int
    missing_count: int
    issues: list[ValidationIssueResponse] = Field(default_factory=list)

