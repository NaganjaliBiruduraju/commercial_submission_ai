"""
Shared FastAPI dependencies.

Injected into route handlers via Depends().
Centralizing dependencies here:
  - Prevents duplication across routers
  - Makes testing easy (dependencies can be overridden via app.dependency_overrides)
  - Enforces RBAC in one place
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import verify_access_token
from app.core.constants import UserRole
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.database.session import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository

# --------------------------------------------------------------------------- #
# Database dependency
# --------------------------------------------------------------------------- #

DatabaseDep = Annotated[AsyncSession, Depends(get_db)]

# --------------------------------------------------------------------------- #
# Bearer token extractor
# --------------------------------------------------------------------------- #

_bearer = HTTPBearer(auto_error=False)

BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None, Depends(_bearer)
]


# --------------------------------------------------------------------------- #
# Auth dependencies
# --------------------------------------------------------------------------- #

async def get_current_user(
    db: DatabaseDep,
    credentials: BearerCredentials,
) -> User:
    """
    Validate the JWT bearer token and return the authenticated User ORM object.

    Raises:
        HTTP 401: Token missing, invalid, or expired.
        HTTP 403: User account is inactive.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = verify_access_token(credentials.credentials)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id_str: str = payload.get("sub", "")
    try:
        user_id = UUID(user_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    repo = UserRepository(db)
    user = await repo.get_by_id_with_role(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Contact your administrator.",
        )

    return user


# Convenience type alias used in route signatures
CurrentUser = Annotated[User, Depends(get_current_user)]


# --------------------------------------------------------------------------- #
# Role guards
# --------------------------------------------------------------------------- #

def _require_roles(*allowed_roles: UserRole):
    """
    Factory that returns a FastAPI dependency function enforcing role membership.

    Usage:
        AdminDep = Annotated[User, Depends(_require_roles(UserRole.ADMIN))]
    """
    async def _check(current_user: CurrentUser) -> User:
        role_name = current_user.role.name if current_user.role else ""
        allowed_values = {r.value for r in allowed_roles}
        if role_name not in allowed_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role(s): {', '.join(allowed_values)}. "
                       f"Your role: {role_name}",
            )
        return current_user
    return _check


async def require_admin(
    current_user: CurrentUser,
) -> User:
    """Require ADMIN role."""
    if not current_user.role or current_user.role.name != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current_user


async def require_underwriter(
    current_user: CurrentUser,
) -> User:
    """Require UNDERWRITER or ADMIN role."""
    allowed = {UserRole.UNDERWRITER.value, UserRole.ADMIN.value}
    role_name = current_user.role.name if current_user.role else ""
    if role_name not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Underwriter or Admin role required",
        )
    return current_user


async def require_reviewer(
    current_user: CurrentUser,
) -> User:
    """Require REVIEWER, UNDERWRITER, or ADMIN role (any authenticated role)."""
    allowed = {
        UserRole.REVIEWER.value,
        UserRole.UNDERWRITER.value,
        UserRole.ADMIN.value,
    }
    role_name = current_user.role.name if current_user.role else ""
    if role_name not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated role required",
        )
    return current_user


# Typed dependency aliases for route signatures
AdminDep = Annotated[User, Depends(require_admin)]
UnderwriterDep = Annotated[User, Depends(require_underwriter)]
ReviewerDep = Annotated[User, Depends(require_reviewer)]
