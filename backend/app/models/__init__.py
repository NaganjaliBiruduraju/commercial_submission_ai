"""
SQLAlchemy ORM model package.

Models are imported here so that Alembic's autogenerate can discover all
tables in a single import. Add every new model to this file.

Phase 1: Stub classes only — no ORM columns yet.
Phase 2+: Real SQLAlchemy mapped models replace the stubs.
"""
# Stubs imported to establish package structure.
# Full ORM models implemented phase by phase.
from app.models.user import User, Role  # noqa: F401
from app.models.submission import Submission  # noqa: F401
from app.models.document import Document, DocumentVersion  # noqa: F401
from app.models.extraction import ExtractedField, Evidence  # noqa: F401
from app.models.validation import ValidationIssue  # noqa: F401
from app.models.risk import RiskAssessment  # noqa: F401
from app.models.knowledge import KnowledgeDocument, KnowledgeChunk  # noqa: F401
from app.models.decision import UnderwriterDecision  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
