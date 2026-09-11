"""
UnderwriterDecision ORM model.

CRITICAL BUSINESS RULE:
  This record can ONLY be created by an authenticated user with
  UNDERWRITER or ADMIN role. The application enforces this at the
  service and API layer with RBAC checks.

  The AI system NEVER creates this record autonomously.
  The AI generates RECOMMENDATIONS — humans record DECISIONS.

  The system must NEVER say:
    "Approved automatically."
    "Rejected automatically."
    "Bind this policy."

  Instead it says:
    "Underwriter review required."
    "Recommended for Senior Underwriter Review."

Decision statuses:
  APPROVED         — Underwriter approves the submission
  DECLINED         — Underwriter declines the submission
  REFERRED         — Referred to senior underwriter
  ADDITIONAL_INFO  — More information requested from broker
  WITHDRAWN        — Broker withdrew the submission

Audit:
  Who made the decision, when, and with what notes is always recorded.
  Previous decisions are retained — overriding a decision creates a new
  record, the old one is soft-replaced via is_current=False.
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import DecisionStatus
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UnderwriterDecision(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "underwriter_decisions"

    __table_args__ = (
        Index("ix_underwriter_decisions_submission_id", "submission_id"),
        Index("ix_underwriter_decisions_decided_by", "decided_by"),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # The decision — only humans can set this
    # -------------------------------------------------------------------------
    decision: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="APPROVED | DECLINED | REFERRED | ADDITIONAL_INFO | WITHDRAWN",
    )
    decision_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Required for DECLINED and REFERRED — explains the decision",
    )
    conditions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Any conditions attached to an APPROVED decision",
    )

    # -------------------------------------------------------------------------
    # Attribution — who decided and when
    # -------------------------------------------------------------------------
    decided_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Must be UNDERWRITER or ADMIN role — enforced at application layer",
    )

    # -------------------------------------------------------------------------
    # Version tracking
    # If a decision is revised, the old record has is_current set to False
    # -------------------------------------------------------------------------
    is_current: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default="true",
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("underwriter_decisions.id", ondelete="SET NULL"),
        nullable=True,
        comment="If this decision was revised, points to the new decision record",
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    decider: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User",
        foreign_keys=[decided_by],
        lazy="noload",
    )

    def __repr__(self) -> str:
        return (
            f"<UnderwriterDecision {self.decision!r} "
            f"submission={self.submission_id} current={self.is_current}>"
        )
