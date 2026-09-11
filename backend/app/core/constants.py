"""
Application-wide constants and enumerations.

Constants here are stable values that do not change per environment.
Configurable thresholds (e.g., risk scores) live in config.py, NOT here.

Using Python Enum for type-safety:
  - IDE auto-complete works correctly
  - Typos in string comparisons are caught at development time
  - Database string values are explicit and auditable
"""
from __future__ import annotations

from enum import Enum


# ---------------------------------------------------------------------------
# User Roles
# ---------------------------------------------------------------------------

class UserRole(str, Enum):
    """
    RBAC roles.

    Using str Enum so these serialize to plain strings in JSON responses
    and database columns without any additional conversion.

    ADMIN:        Full system access — user management, knowledge base, config
    UNDERWRITER:  Can review submissions, override extractions, set decisions
    REVIEWER:     Read-only access to submissions and documents
    """
    ADMIN = "ADMIN"
    UNDERWRITER = "UNDERWRITER"
    REVIEWER = "REVIEWER"


# ---------------------------------------------------------------------------
# Document Types
# ---------------------------------------------------------------------------

class DocumentType(str, Enum):
    """
    Classification categories for uploaded documents.

    The classifier assigns one of these types to every document.
    Document-type-specific extractors are then selected accordingly.
    """
    ACORD_APPLICATION = "ACORD_APPLICATION"    # ACORD 125
    ACORD_GL = "ACORD_GL"                      # ACORD 126 General Liability
    ACORD_PROPERTY = "ACORD_PROPERTY"          # ACORD 140 Property
    ACORD_AUTO = "ACORD_AUTO"                  # ACORD 127 Business Auto
    ACORD_WORKERS_COMP = "ACORD_WORKERS_COMP"  # ACORD 130 Workers Compensation
    ACORD_UMBRELLA = "ACORD_UMBRELLA"          # ACORD 131 Umbrella/Excess
    LOSS_RUN = "LOSS_RUN"                      # Claims history report
    FINANCIAL_STATEMENT = "FINANCIAL_STATEMENT"
    BROKER_EMAIL = "BROKER_EMAIL"
    UNDERWRITING_GUIDELINE = "UNDERWRITING_GUIDELINE"
    CLAIMS_DOCUMENT = "CLAIMS_DOCUMENT"
    EVIDENCE_PHOTO = "EVIDENCE_PHOTO"
    IDENTITY_DOCUMENT = "IDENTITY_DOCUMENT"
    OTHER = "OTHER"


# ---------------------------------------------------------------------------
# Submission Processing Status
# ---------------------------------------------------------------------------

class SubmissionStatus(str, Enum):
    """
    Processing states for a submission.

    A submission transitions through these states as the pipeline progresses.
    The UI displays these states to show processing progress.
    FAILED is terminal — the submission must be re-submitted or manually remediated.
    """
    UPLOADED = "UPLOADED"
    VALIDATING = "VALIDATING"
    PARSING = "PARSING"
    OCR_PROCESSING = "OCR_PROCESSING"
    CLASSIFYING = "CLASSIFYING"
    EXTRACTING = "EXTRACTING"
    VALIDATING_DATA = "VALIDATING_DATA"
    RETRIEVING_GUIDELINES = "RETRIEVING_GUIDELINES"
    ANALYZING = "ANALYZING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    UNDER_REVIEW = "UNDER_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Document Processing Status
# ---------------------------------------------------------------------------

class DocumentProcessingStatus(str, Enum):
    """Individual document processing states."""
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    PARSING = "PARSING"
    OCR_PROCESSING = "OCR_PROCESSING"
    CLASSIFYING = "CLASSIFYING"
    EXTRACTING = "EXTRACTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"


# ---------------------------------------------------------------------------
# Validation Issue Types
# ---------------------------------------------------------------------------

class ValidationIssueType(str, Enum):
    """
    Categories of deterministic validation issues.

    These are calculated by Python — not by the LLM.
    """
    CONFLICT = "CONFLICT"           # Two documents report different values for same field
    MISSING = "MISSING"             # Required field absent from all documents
    INVALID = "INVALID"             # Field present but fails validation rule
    WARNING = "WARNING"             # Non-blocking concern for underwriter attention


class ValidationSeverity(str, Enum):
    """How serious the validation issue is."""
    ERROR = "ERROR"       # Must be resolved before underwriting proceeds
    WARNING = "WARNING"   # Underwriter should review but can proceed
    INFO = "INFO"         # Informational — no action required


# ---------------------------------------------------------------------------
# Risk Categories
# ---------------------------------------------------------------------------

class RiskCategory(str, Enum):
    """
    Risk assessment categories.

    Thresholds are configured in settings — NOT hard-coded here.
    These enum values represent the categories, not the thresholds.
    [DEMO RULE — real thresholds require approved underwriting authority]
    """
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNDETERMINED = "UNDETERMINED"   # Insufficient data to calculate score


# ---------------------------------------------------------------------------
# Underwriter Decision Status
# ---------------------------------------------------------------------------

class DecisionStatus(str, Enum):
    """
    Final underwriting decision options.

    CRITICAL: Only an authenticated UNDERWRITER or ADMIN can set these.
    The AI system NEVER sets a final decision autonomously.
    The AI may RECOMMEND but humans DECIDE.
    """
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    REFERRED = "REFERRED"             # Referred to senior underwriter
    ADDITIONAL_INFO = "ADDITIONAL_INFO"  # More info needed from broker
    WITHDRAWN = "WITHDRAWN"           # Broker withdrew the submission


# ---------------------------------------------------------------------------
# AI Recommendation Types (NOT final decisions)
# ---------------------------------------------------------------------------

class AIRecommendation(str, Enum):
    """
    AI-generated recommendation types.

    These are suggestions for the human underwriter — NOT decisions.
    The system NEVER automatically acts on these.
    """
    STANDARD_REVIEW = "STANDARD_REVIEW"
    SENIOR_REVIEW = "SENIOR_REVIEW"
    ADDITIONAL_INFO_REQUIRED = "ADDITIONAL_INFO_REQUIRED"
    SPECIALIST_REVIEW = "SPECIALIST_REVIEW"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


# ---------------------------------------------------------------------------
# Knowledge Document Status
# ---------------------------------------------------------------------------

class KnowledgeDocumentStatus(str, Enum):
    """
    Lifecycle states for knowledge base documents.

    Only ACTIVE documents may be retrieved for RAG.
    DRAFT and PENDING_APPROVAL documents are visible in the admin UI only.
    EXPIRED documents are retained for audit but excluded from RAG retrieval.
    """
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


# ---------------------------------------------------------------------------
# Audit Action Types
# ---------------------------------------------------------------------------

class AuditAction(str, Enum):
    """
    Types of auditable actions.

    Every important state change generates an AuditLog record with one of
    these action types. This provides a forensic-quality trail.
    """
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    DELETED = "DELETED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REFERRED = "REFERRED"
    OVERRIDDEN = "OVERRIDDEN"         # Underwriter overrode an AI extraction
    RESOLVED = "RESOLVED"             # Underwriter resolved a validation issue
    UPLOADED = "UPLOADED"
    PROCESSED = "PROCESSED"
    CLASSIFIED = "CLASSIFIED"
    EXTRACTED = "EXTRACTED"
    INDEXED = "INDEXED"               # Knowledge document indexed for RAG
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    ROLE_CHANGED = "ROLE_CHANGED"


# ---------------------------------------------------------------------------
# Processing Stages (for observability logging)
# ---------------------------------------------------------------------------

class ProcessingStage(str, Enum):
    """
    Pipeline processing stages used in structured log entries.
    Every log entry from a processing operation includes one of these.
    """
    FILE_VALIDATION = "FILE_VALIDATION"
    INGESTION = "INGESTION"
    PARSING = "PARSING"
    OCR = "OCR"
    CLASSIFICATION = "CLASSIFICATION"
    EXTRACTION = "EXTRACTION"
    EVIDENCE_MAPPING = "EVIDENCE_MAPPING"
    VALIDATION = "VALIDATION"
    RAG_RETRIEVAL = "RAG_RETRIEVAL"
    EMBEDDING = "EMBEDDING"
    RISK_SCORING = "RISK_SCORING"
    SUMMARIZATION = "SUMMARIZATION"
    LLM_CALL = "LLM_CALL"


# ---------------------------------------------------------------------------
# Allowed MIME Types
# ---------------------------------------------------------------------------

ALLOWED_MIME_TYPES: frozenset[str] = frozenset({
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",        # xlsx
    "application/vnd.ms-excel",                                                 # xls
    "text/csv",
    "text/plain",
    "image/jpeg",
    "image/jpg",
    "image/png",
})

# Map file extensions to expected MIME types (for validation)
EXTENSION_TO_MIME: dict[str, str] = {
    "pdf":  "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls":  "application/vnd.ms-excel",
    "csv":  "text/csv",
    "jpg":  "image/jpeg",
    "jpeg": "image/jpeg",
    "png":  "image/png",
}

# ---------------------------------------------------------------------------
# API Response Codes
# ---------------------------------------------------------------------------

class ErrorCode(str, Enum):
    """
    Machine-readable error codes for API responses.
    These appear in the 'error.code' field of error responses.
    """
    INTERNAL_ERROR = "INTERNAL_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    DOCUMENT_VALIDATION_ERROR = "DOCUMENT_VALIDATION_ERROR"
    DOCUMENT_PARSING_ERROR = "DOCUMENT_PARSING_ERROR"
    OCR_ERROR = "OCR_ERROR"
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    LLM_ERROR = "LLM_ERROR"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_RATE_LIMIT = "LLM_RATE_LIMIT"
    LLM_RESPONSE_VALIDATION_ERROR = "LLM_RESPONSE_VALIDATION_ERROR"
    PROMPT_INJECTION_DETECTED = "PROMPT_INJECTION_DETECTED"
    RAG_ERROR = "RAG_ERROR"
    EMBEDDING_ERROR = "EMBEDDING_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    LLM_NOT_CONFIGURED = "LLM_NOT_CONFIGURED"
