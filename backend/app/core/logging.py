"""
Structured application logging.

Why structured logging?
  - Every log entry is a JSON object with consistent fields
  - Log entries can be queried, filtered, and aggregated by log management systems
  - Observability is a first-class requirement for this system
  - Secrets are NEVER logged — this is enforced by the logger configuration

Log entry fields:
  timestamp   - ISO 8601 UTC
  level       - DEBUG / INFO / WARNING / ERROR / CRITICAL
  request_id  - UUID per HTTP request (set in middleware)
  submission_id - UUID of the submission being processed (when applicable)
  document_id - UUID of the document being processed (when applicable)
  stage       - Processing stage (PARSING, OCR, EXTRACTION, etc.)
  duration_ms - Processing duration in milliseconds (when applicable)
  status      - SUCCESS / FAILURE
  message     - Human-readable description
  error_code  - Machine-readable error code (no stack trace in production)

NEVER LOG:
  - API keys (GROQ_API_KEY or any other)
  - Passwords or hashed passwords
  - JWT tokens or secrets
  - Full PII unnecessarily
  - Stack traces in production API responses (only in backend logs)
"""
from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Context variables — set per request by middleware
# ---------------------------------------------------------------------------

# These are thread-safe ContextVars — each async task has its own value.
# Set in request middleware; read by the log formatter.
_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
_submission_id_var: ContextVar[str | None] = ContextVar("submission_id", default=None)
_document_id_var: ContextVar[str | None] = ContextVar("document_id", default=None)


def set_log_context(
    request_id: str | None = None,
    submission_id: str | None = None,
    document_id: str | None = None,
) -> None:
    """Set per-request context variables for log enrichment."""
    if request_id:
        _request_id_var.set(request_id)
    if submission_id:
        _submission_id_var.set(submission_id)
    if document_id:
        _document_id_var.set(document_id)


def get_request_id() -> str:
    """Return the current request ID or generate a new one."""
    return _request_id_var.get() or str(uuid.uuid4())


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------

class JSONFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.

    Uses stdlib json rather than a third-party library to minimize
    startup dependencies in Phase 1.
    """

    # Fields that should NEVER appear in log output
    _FORBIDDEN_FIELDS = frozenset({
        "groq_api_key", "api_key", "secret_key", "password", "hashed_password",
        "token", "access_token", "refresh_token", "jwt", "authorization",
        "cookie", "session",
    })

    def format(self, record: logging.LogRecord) -> str:
        import json  # local import — json is stdlib, always available

        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": _request_id_var.get(),
            "submission_id": _submission_id_var.get(),
            "document_id": _document_id_var.get(),
        }

        # Add structured extras passed via logger.info(..., extra={...})
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            }:
                continue
            # NEVER log forbidden field names
            if key.lower() in self._FORBIDDEN_FIELDS:
                entry[key] = "[REDACTED]"
                continue
            entry[key] = value

        # Include exception info in development
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, default=str)


class TextFormatter(logging.Formatter):
    """
    Human-readable formatter for development console output.
    Easier to read than JSON when running locally.
    """

    _FMT = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    def __init__(self) -> None:
        super().__init__(fmt=self._FMT, datefmt="%H:%M:%S")


# ---------------------------------------------------------------------------
# Logger factory
# ---------------------------------------------------------------------------

def configure_logging(
    level: str = "INFO",
    log_format: str = "json",
    log_file: str | None = None,
) -> None:
    """
    Configure the root logger for the application.

    Call once at application startup in main.py.
    Subsequent calls to get_logger() will inherit this configuration.

    Args:
        level:      Log level string (DEBUG / INFO / WARNING / ERROR / CRITICAL)
        log_format: "json" for structured output, "text" for human-readable
        log_file:   Optional path to write logs to disk. None = stdout only.
    """
    formatter: logging.Formatter = (
        JSONFormatter() if log_format == "json" else TextFormatter()
    )

    handlers: list[logging.Handler] = []

    # Always log to stdout
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    handlers.append(stdout_handler)

    # Optionally also log to a file
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=handlers,
        force=True,  # Replace any existing handlers
    )

    # Quiet noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger.

    Usage:
        from app.core.logging import get_logger
        logger = get_logger(__name__)
        logger.info("Processing document", extra={"stage": "PARSING", "document_id": doc_id})
    """
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Processing stage logger helper
# ---------------------------------------------------------------------------

class StageLogger:
    """
    Context manager for timing and logging a processing stage.

    Usage:
        async with StageLogger(logger, "PARSING", submission_id=sid, document_id=did):
            result = await parse_document(doc)

    On exit, logs the stage result with duration_ms and status.
    Handles exceptions by logging FAILURE before re-raising.
    """

    def __init__(
        self,
        logger: logging.Logger,
        stage: str,
        submission_id: str | None = None,
        document_id: str | None = None,
    ) -> None:
        self._logger = logger
        self._stage = stage
        self._submission_id = submission_id
        self._document_id = document_id
        self._start: float = 0.0

    async def __aenter__(self) -> "StageLogger":
        import time
        self._start = time.monotonic()
        self._logger.info(
            f"Stage started: {self._stage}",
            extra={
                "stage": self._stage,
                "status": "STARTED",
                "submission_id": self._submission_id,
                "document_id": self._document_id,
            },
        )
        return self

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: Exception | None,
        exc_tb: object | None,
    ) -> bool:
        import time
        duration_ms = int((time.monotonic() - self._start) * 1000)

        if exc_val is None:
            self._logger.info(
                f"Stage completed: {self._stage}",
                extra={
                    "stage": self._stage,
                    "status": "SUCCESS",
                    "duration_ms": duration_ms,
                    "submission_id": self._submission_id,
                    "document_id": self._document_id,
                },
            )
        else:
            # Log the error but never include secrets in the log entry
            self._logger.error(
                f"Stage failed: {self._stage} — {type(exc_val).__name__}",
                extra={
                    "stage": self._stage,
                    "status": "FAILURE",
                    "duration_ms": duration_ms,
                    "error_type": type(exc_val).__name__,
                    # Do NOT log exc_val.args directly — may contain sensitive data
                    "submission_id": self._submission_id,
                    "document_id": self._document_id,
                },
            )

        return False  # Do not suppress the exception
