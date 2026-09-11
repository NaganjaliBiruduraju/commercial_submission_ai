"""
Base Pydantic schemas and the standard API response envelope.

Every API response is wrapped in APIResponse[T] for consistency.
This means:
  - Success responses always have success=True, data=T, error=None
  - Error responses always have success=False, data=None, error=ErrorDetail
  - Every response carries a request_id for log correlation

Why a generic envelope?
  Frontend code can rely on a predictable shape regardless of endpoint.
  Error handling is uniform across all clients.
  request_id enables log correlation between client and server.

Usage in route handlers:
    return APIResponse[SubmissionResponse](
        data=submission,
        request_id=request.state.request_id,
    )
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class InsightBaseModel(BaseModel):
    """
    Base model for all INSIGHT AI schemas.

    model_config settings:
      from_attributes=True  — allows constructing from SQLAlchemy ORM objects
      populate_by_name=True — allows both alias and field name
      str_strip_whitespace  — silently strip leading/trailing whitespace
    """
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class ErrorDetail(InsightBaseModel):
    """Machine-readable error detail included in error responses."""
    code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable error description")
    field: str | None = Field(
        default=None,
        description="Field name if this is a field-level validation error",
    )


class APIResponse(InsightBaseModel, Generic[T]):
    """
    Standard API response envelope.

    All endpoints return this shape. Frontend code checks success first,
    then reads data on success or error on failure.

    Example success:
        {"success": true, "data": {...}, "error": null, "request_id": "uuid"}

    Example error:
        {"success": false, "data": null, "error": {"code": "...", "message": "..."}, "request_id": "uuid"}
    """
    success: bool = Field(description="True if the request succeeded")
    data: T | None = Field(default=None, description="Response payload on success")
    error: ErrorDetail | None = Field(default=None, description="Error detail on failure")
    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="UUID for correlating this response with backend logs",
    )

    @classmethod
    def ok(cls, data: T, request_id: str | None = None) -> "APIResponse[T]":
        """Convenience constructor for successful responses."""
        return cls(
            success=True,
            data=data,
            error=None,
            request_id=request_id or str(uuid.uuid4()),
        )

    @classmethod
    def fail(
        cls,
        code: str,
        message: str,
        request_id: str | None = None,
        field: str | None = None,
    ) -> "APIResponse[None]":
        """Convenience constructor for error responses."""
        return cls(
            success=False,
            data=None,
            error=ErrorDetail(code=code, message=message, field=field),
            request_id=request_id or str(uuid.uuid4()),
        )


class PaginatedResponse(InsightBaseModel, Generic[T]):
    """Paginated list response wrapper."""
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedResponse[T]":
        pages = max(1, (total + page_size - 1) // page_size)
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)


class TimestampSchema(InsightBaseModel):
    """Mixin schema for created_at / updated_at fields."""
    created_at: datetime
    updated_at: datetime
