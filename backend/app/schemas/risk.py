"""
Risk assessment Pydantic schemas.

The risk score is calculated by Python — the LLM explains it.
score_breakdown provides full transparency into every contributing factor.
"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import Field

from app.schemas.base import InsightBaseModel, TimestampSchema
from app.core.constants import RiskCategory, AIRecommendation


class RiskFactor(InsightBaseModel):
    """A single factor contributing to the risk score."""
    name: str
    delta: int = Field(description="Score change: positive increases risk, negative reduces it")
    reason: str
    evidence: str | None = None


class RiskScoreBreakdown(InsightBaseModel):
    """Transparent risk score calculation record."""
    base_score: int
    factors: list[RiskFactor] = Field(default_factory=list)
    final_score: int = Field(ge=0, le=100)
    category: RiskCategory
    thresholds_used: dict[str, int]
    threshold_source: str = Field(
        description="e.g. 'DEMO RULE — NOT APPROVED POLICY' or approved guideline reference"
    )


class RiskAssessmentResponse(InsightBaseModel, TimestampSchema):
    """Full risk assessment for a submission."""
    id: uuid.UUID
    submission_id: uuid.UUID
    risk_score: int | None = Field(default=None, ge=0, le=100)
    risk_category: RiskCategory
    score_breakdown: RiskScoreBreakdown | None = None

    # LLM-generated explanation — clearly labelled as AI output
    score_explanation: str | None = Field(
        default=None,
        description="AI-generated explanation — not a substitute for underwriter judgment",
    )
    ai_recommendation: AIRecommendation | None = None
    ai_recommendation_rationale: str | None = None
    calculated_by_model: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
