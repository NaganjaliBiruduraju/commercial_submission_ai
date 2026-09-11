"""
AuthService — login, token refresh, and password management.

Business logic only. No HTTP / FastAPI concerns here.
The service receives a DB session from the caller and uses repositories
to access data.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import (
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
)
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.logging import get_logger
from app.core.security import hash_password, needs_rehash, verify_password
from app.repositories.user_repository import UserRepository
from app.schemas.user import TokenResponse

logger = get_logger(__name__)


class AuthService:
    """
    Handles all authentication operations.

    Injected with an AsyncSession; creates repositories internally.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)

    async def login(self, email: str, password: str) -> TokenResponse:
        """
        Authenticate user and return access + refresh tokens.

        Steps:
          1. Look up user by email.
          2. Verify password.
          3. Check account is active.
          4. Transparently rehash if bcrypt cost factor has changed.
          5. Update last_login timestamp.
          6. Issue tokens.

        Raises:
            AuthenticationError: Wrong credentials or inactive account.
        """
        settings = get_settings()

        # Use a generic error message — never reveal whether the email exists
        _bad_credentials = AuthenticationError(
            "Incorrect email or password"
        )

        user = await self.user_repo.get_by_email(email)
        if user is None:
            # Still call verify_password with a dummy hash to prevent
            # timing attacks that could reveal whether the email exists.
            verify_password(password, "$2b$12$dummyhashtopreventtimingattacks000000000000")
            raise _bad_credentials

        if not verify_password(password, user.hashed_password):
            logger.warning("Failed login attempt", email=email)
            raise _bad_credentials

        if not user.is_active:
            raise AuthorizationError("Account is disabled. Contact your administrator.")

        # Transparent rehash if bcrypt cost factor has been updated
        if needs_rehash(user.hashed_password):
            user.hashed_password = hash_password(password)
            logger.info("Password rehashed for user", user_id=str(user.id))

        # Record last login
        user.last_login = datetime.now(tz=timezone.utc)
        await self.db.commit()
        await self.db.refresh(user)

        # Ensure role is loaded
        role_name = user.role.name if user.role else "UNKNOWN"

        access_token = create_access_token(
            subject=str(user.id),
            role=role_name,
        )
        refresh_token = create_refresh_token(subject=str(user.id))

        logger.info("User logged in", user_id=str(user.id), role=role_name)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        )

    async def refresh_tokens(self, refresh_token: str) -> TokenResponse:
        """
        Issue a new access + refresh token pair given a valid refresh token.

        The old refresh token is NOT revoked (stateless JWT design — Phase 15
        will add token rotation with a revocation list if needed).

        Raises:
            AuthenticationError: Invalid/expired refresh token or missing user.
        """
        settings = get_settings()

        payload = verify_refresh_token(refresh_token)  # raises on invalid
        user_id_str: str = payload["sub"]

        try:
            user_id = UUID(user_id_str)
        except ValueError as exc:
            raise AuthenticationError("Malformed token subject") from exc

        user = await self.user_repo.get_by_id_with_role(user_id)
        if user is None:
            raise AuthenticationError("User not found")

        if not user.is_active:
            raise AuthorizationError("Account is disabled")

        role_name = user.role.name if user.role else "UNKNOWN"

        new_access = create_access_token(subject=str(user.id), role=role_name)
        new_refresh = create_refresh_token(subject=str(user.id))

        logger.info("Tokens refreshed", user_id=str(user.id))

        return TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        )
