"""
RiskAssessment model.

Stores the risk score, category, and factor breakdown for a submission.
The risk score (0-100) is calculated by Python — not by the LLM.
The score_breakdown field is a JSON record of every contributing factor
and its weight, providing a transparent, auditable calculation.
The score_explanation field contains LLM-generated text explaining the score
in underwriting language.

Thresholds (LOW/MEDIUM/HIGH) are loaded from configuration — never hard-coded.

Implemented fully in Phase 16: Risk Analysis.
"""
from __future__ import annotations


class RiskAssessment:
    """Placeholder — implemented in Phase 16."""
    pass
