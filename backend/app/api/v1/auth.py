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
from app.schemas.user import LoginRequest, RefreshRequest, TokenResponse, UserResponse, UserCreate, UserRegister
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.core.logging import get_logger
from app.core.constants import UserRole

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=APIResponse[TokenResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Create a new user account and receive JWT tokens. "
        "Public endpoint - no authentication required. "
        "New users are assigned USER role by default."
    ),
)
async def register(
    payload: UserRegister,
    db: DatabaseDep,
) -> APIResponse[TokenResponse]:
    """Register a new user and return tokens."""
    user_svc = UserService(db)
    auth_svc = AuthService(db)
    
    # Create UserCreate with default USER role
    user_create = UserCreate(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=UserRole.USER,  # Default role for registration
    )
    
    # Create the user (no created_by_id for self-registration)
    user = await user_svc.create_user(user_create, created_by_id=None)
    
    # Automatically log them in
    token_data = await auth_svc.login(payload.email, payload.password)
    
    logger.info("New user registered", user_id=str(user.id), email=payload.email)
    return APIResponse.ok(token_data)


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
