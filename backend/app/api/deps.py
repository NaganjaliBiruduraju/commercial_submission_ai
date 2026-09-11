"""
Shared FastAPI dependencies.

These are injected into route handlers via Depends().
Centralizing dependencies here prevents duplication across routers
and makes testing easier (dependencies can be overridden in tests).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.auth.jwt import verify_access_token
from app.core.exceptions import AuthenticationError, AuthorizationError

# ---------------------------------------------------------------------------
# Database dependency
# ---------------------------------------------------------------------------

DatabaseDep = Annotated[AsyncSession, Depends(get_db)]

# ---------------------------------------------------------------------------
# Auth dependencies — Phase 2 will fully implement these
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    db: DatabaseDep,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> "User":  # type: ignore[name-defined]  # noqa: F821
    """
    Validate the JWT bearer token and return the authenticated User.
    Raises HTTP 401 if the token is missing or invalid.
    Raises HTTP 403 if the user account is inactive.
    Implemented fully in Phase 2.
    """
    # Stub — Phase 2 implementation
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Authentication not yet implemented — Phase 2",
    )


async def require_admin(current_user: Annotated["User", Depends(get_current_user)]) -> "User":  # type: ignore[name-defined]  # noqa: F821
    """Require ADMIN role."""
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)


async def require_underwriter(current_user: Annotated["User", Depends(get_current_user)]) -> "User":  # type: ignore[name-defined]  # noqa: F821
    """Require UNDERWRITER or ADMIN role."""
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)


async def require_reviewer(current_user: Annotated["User", Depends(get_current_user)]) -> "User":  # type: ignore[name-defined]  # noqa: F821
    """Require REVIEWER, UNDERWRITER, or ADMIN role."""
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)
