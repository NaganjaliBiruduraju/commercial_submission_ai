"""
User and Role Pydantic schemas.

Security rules enforced here:
  - hashed_password is NEVER included in any response schema
  - Passwords are validated for minimum strength on creation
  - Email is normalized to lowercase before storage
  - Role is returned as a nested object, not just an ID
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from app.schemas.base import InsightBaseModel, TimestampSchema
from app.core.constants import UserRole


# ---------------------------------------------------------------------------
# Role schemas
# ---------------------------------------------------------------------------

class RoleResponse(TimestampSchema, InsightBaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------

class UserCreate(InsightBaseModel):
    """Request body for creating a new user (admin only)."""
    email: EmailStr
    password: str = Field(min_length=8, description="Minimum 8 characters")
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if v.isdigit():
            raise ValueError("Password cannot be all digits")
        return v


class UserUpdate(InsightBaseModel):
    """Request body for updating a user. All fields optional."""
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    role: UserRole | None = None


class UserPasswordChange(InsightBaseModel):
    """Request body for changing own password."""
    current_password: str
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if v.isdigit():
            raise ValueError("Password cannot be all digits")
        return v


class UserResponse(TimestampSchema, InsightBaseModel):
    """
    User as returned in API responses.
    NEVER includes hashed_password or any credential fields.
    """
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    last_login: datetime | None = None
    role: RoleResponse


class UserSummary(InsightBaseModel):
    """Compact user representation for embedding in other responses."""
    id: uuid.UUID
    email: str
    full_name: str
    role_name: str


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------

class LoginRequest(InsightBaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return v.lower().strip()


class TokenResponse(InsightBaseModel):
    """Returned on successful login."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class RefreshRequest(InsightBaseModel):
    refresh_token: str

