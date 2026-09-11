"""
Auth router — /api/v1/auth

Endpoints:
  POST /login       — exchange credentials for tokens
  POST /refresh     — exchange refresh token for new token pair
  POST /logout      — client-side token discard (stateless JWT)
  GET  /me          — return current user profile

No business logic here — delegate to AuthService.
"""
from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DatabaseDep
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.schemas.base import APIResponse
from app.schemas.user import LoginRequest, RefreshRequest, TokenResponse, UserResponse
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=APIResponse[TokenResponse],
    status_code=status.HTTP_200_OK,
    summary="Login and receive JWT tokens",
    description=(
        "Authenticate with email + password. "
        "Returns a short-lived access token (15 min) and a long-lived refresh token (7 days)."
    ),
)
async def login(
    payload: LoginRequest,
    db: DatabaseDep,
) -> APIResponse[TokenResponse]:
    svc = AuthService(db)
    token_data = await svc.login(payload.email, payload.password)
    return APIResponse.ok(token_data)


@router.post(
    "/refresh",
    response_model=APIResponse[TokenResponse],
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description=(
        "Exchange a valid refresh token for a new access + refresh token pair. "
        "The old refresh token remains valid until its expiry (stateless design)."
    ),
)
async def refresh_tokens(
    payload: RefreshRequest,
    db: DatabaseDep,
) -> APIResponse[TokenResponse]:
    svc = AuthService(db)
    token_data = await svc.refresh_tokens(payload.refresh_token)
    return APIResponse.ok(token_data)


@router.post(
    "/logout",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Logout (client-side token discard)",
    description=(
        "Instructs the client to discard its tokens. "
        "Tokens remain cryptographically valid until expiry (stateless JWT). "
        "Phase 15 will add server-side token revocation."
    ),
)
async def logout(
    current_user: CurrentUser,
) -> APIResponse[None]:
    logger.info("User logged out", user_id=str(current_user.id))
    return APIResponse.ok(None)


@router.get(
    "/me",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
)
async def get_me(
    current_user: CurrentUser,
    db: DatabaseDep,
) -> APIResponse[UserResponse]:
    svc = UserService(db)
    user_data = await svc.get_me(current_user.id)
    return APIResponse.ok(user_data)
