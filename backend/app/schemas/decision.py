"""
Underwriter decision and audit log Pydantic schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.base import InsightBaseModel, TimestampSchema
from app.core.constants import DecisionStatus, AuditAction
from app.schemas.user import UserSummary


class UnderwriterDecisionCreate(InsightBaseModel):
    """
    Request body for recording an underwriter decision.

    CRITICAL: The backend enforces that only UNDERWRITER or ADMIN
    roles can call the endpoint that uses this schema.
    The AI NEVER submits this — only authenticated human users do.
    """
    decision: DecisionStatus
    decision_notes: str | None = Field(
        default=None,
        description="Required for DECLINED and REFERRED decisions",
    )
    conditions: str | None = Field(
        default=None,
        description="Conditions attached to an APPROVED decision",
    )


class UnderwriterDecisionResponse(InsightBaseModel, TimestampSchema):
    id: uuid.UUID
    submission_id: uuid.UUID
    decision: DecisionStatus
    decision_notes: str | None = None
    conditions: str | None = None
    decided_by: uuid.UUID
    decider: UserSummary | None = None
    is_current: bool
    superseded_by: uuid.UUID | None = None


class AuditLogResponse(InsightBaseModel):
    """Audit log entry for display in the UI audit history panel."""
    id: uuid.UUID
    created_at: datetime
    action: AuditAction
    entity_type: str
    entity_id: uuid.UUID | None = None
    actor_id: uuid.UUID | None = None
    actor: UserSummary | None = None
    old_value: dict | None = None
    new_value: dict | None = None
    reason: str | None = None
    submission_id: uuid.UUID | None = None
    request_id: str | None = None
