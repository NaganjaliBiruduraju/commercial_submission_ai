"""
Application-wide exception hierarchy.

Centralizing exceptions here ensures:
  1. Consistent error codes throughout the API
  2. A single place to map domain errors to HTTP status codes
  3. No raw Python exceptions leaking to API responses

All custom exceptions inherit from InsightAIError.
FastAPI exception handlers in main.py convert these to standard API responses.
"""
from __future__ import annotations


class InsightAIError(Exception):
    """Base exception for all INSIGHT AI application errors."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Authentication and Authorization
# ---------------------------------------------------------------------------

class AuthenticationError(InsightAIError):
    """Raised when credentials are invalid or token has expired."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, code="AUTHENTICATION_ERROR")


class AuthorizationError(InsightAIError):
    """Raised when the user lacks the required role or permission."""

    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(message, code="AUTHORIZATION_ERROR")


# ---------------------------------------------------------------------------
# Document Processing
# ---------------------------------------------------------------------------

class DocumentValidationError(InsightAIError):
    """Raised when an uploaded file fails validation (type, size, count, corruption)."""

    def __init__(self, message: str, filename: str | None = None) -> None:
        self.filename = filename
        super().__init__(message, code="DOCUMENT_VALIDATION_ERROR")


class DocumentParsingError(InsightAIError):
    """Raised when a document cannot be parsed (corrupted PDF, unreadable DOCX, etc.)."""

    def __init__(self, message: str, document_id: str | None = None) -> None:
        self.document_id = document_id
        super().__init__(message, code="DOCUMENT_PARSING_ERROR")


class OCRError(InsightAIError):
    """Raised when OCR processing fails on a scanned document or image."""

    def __init__(self, message: str, document_id: str | None = None) -> None:
        self.document_id = document_id
        super().__init__(message, code="OCR_ERROR")


class UnsupportedFileTypeError(InsightAIError):
    """Raised when an uploaded file has an unsupported MIME type or extension."""

    def __init__(self, file_type: str) -> None:
        self.file_type = file_type
        super().__init__(
            f"Unsupported file type: {file_type}",
            code="UNSUPPORTED_FILE_TYPE",
        )


# ---------------------------------------------------------------------------
# AI and LLM
# ---------------------------------------------------------------------------

class LLMError(InsightAIError):
    """Base exception for LLM-related failures."""

    def __init__(self, message: str, code: str = "LLM_ERROR") -> None:
        super().__init__(message, code)


class LLMTimeoutError(LLMError):
    """Raised when the LLM API call exceeds the configured timeout."""

    def __init__(self, timeout_seconds: int) -> None:
        super().__init__(
            f"LLM request timed out after {timeout_seconds}s",
            code="LLM_TIMEOUT",
        )


class LLMRateLimitError(LLMError):
    """Raised when the LLM API returns a rate limit error (retriable)."""

    def __init__(self) -> None:
        super().__init__("LLM API rate limit exceeded", code="LLM_RATE_LIMIT")


class LLMResponseValidationError(LLMError):
    """
    Raised when the LLM response does not conform to the expected output schema.
    This is NOT retriable without changing the prompt — it indicates a schema mismatch.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, code="LLM_RESPONSE_VALIDATION_ERROR")


class PromptInjectionDetectedError(InsightAIError):
    """
    Raised when suspicious prompt-injection patterns are detected in document content.
    The document is NOT sent to the LLM. Processing is halted and a warning is logged.
    """

    def __init__(self, document_id: str | None = None) -> None:
        self.document_id = document_id
        super().__init__(
            "Potential prompt injection detected in document content. Processing halted.",
            code="PROMPT_INJECTION_DETECTED",
        )


# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------

class RAGError(InsightAIError):
    """Raised when RAG retrieval fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="RAG_ERROR")


class EmbeddingError(InsightAIError):
    """Raised when embedding generation fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="EMBEDDING_ERROR")


# ---------------------------------------------------------------------------
# Data / Business Logic
# ---------------------------------------------------------------------------

class NotFoundError(InsightAIError):
    """Raised when a requested resource does not exist."""

    def __init__(self, resource: str, resource_id: str) -> None:
        super().__init__(
            f"{resource} not found: {resource_id}",
            code="NOT_FOUND",
        )


class ValidationError(InsightAIError):
    """Raised when input data fails business rule validation."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="VALIDATION_ERROR")


class ConfigurationError(InsightAIError):
    """Raised when a required configuration value is missing or invalid."""

    def __init__(self, key: str) -> None:
        super().__init__(
            f"Configuration error: missing or invalid value for '{key}'",
            code="CONFIGURATION_ERROR",
        )
