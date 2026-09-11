"""
UnderwriterDecision model.

Records the final underwriting decision made by an authorized human underwriter.

CRITICAL: This record can ONLY be created by an authenticated user with
UNDERWRITER or ADMIN role. The AI system can NEVER create this record
autonomously. The AI may suggest, but the human records the decision.

Decision statuses:
  APPROVED         - Underwriter approves the submission
  DECLINED         - Underwriter declines the submission
  REFERRED         - Referred to senior underwriter for review
  ADDITIONAL_INFO  - Additional information requested from broker
  WITHDRAWN        - Submission withdrawn by broker

Implemented fully in Phase 18: Human Review Workflow.
"""
from __future__ import annotations


class UnderwriterDecision:
    """Placeholder — implemented in Phase 18."""
    pass
