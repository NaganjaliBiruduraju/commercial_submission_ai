"""
SQLAlchemy ORM model package.

All models are imported here so Alembic autogenerate discovers every table
in a single import chain:
  alembic/env.py → app.database.base → app.models → (all model files)

Import order matters: models with no foreign-key dependencies first,
then models that depend on them.
"""
# Base and mixins — no dependencies
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, CreatedByMixin  # noqa: F401

# Independent domain models
from app.models.user import Role, User  # noqa: F401
from app.models.submission import Submission  # noqa: F401
from app.models.document import Document, DocumentVersion  # noqa: F401
from app.models.knowledge import KnowledgeDocument, KnowledgeChunk  # noqa: F401

# Models that depend on the above
from app.models.extraction import ExtractedField, Evidence  # noqa: F401
from app.models.validation import ValidationIssue  # noqa: F401
from app.models.risk import RiskAssessment  # noqa: F401
from app.models.decision import UnderwriterDecision  # noqa: F401

# Audit — depends on User, should be last
from app.models.audit import AuditLog  # noqa: F401
