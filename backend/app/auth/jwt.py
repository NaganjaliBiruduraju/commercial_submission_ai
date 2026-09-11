"""
JWT token creation and verification.

Access tokens:  short-lived (default 15 min), carry user_id + role.
Refresh tokens: long-lived (default 7 days), carry only user_id.

All tokens are signed with HS256 using SECRET_KEY from settings.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.logging import get_logger

logger = get_logger(__name__)

# --------------------------------------------------------------------------- #
# Token payload field names
# --------------------------------------------------------------------------- #
_SUB = "sub"           # user UUID (str)
_ROLE = "role"         # UserRole value
_TYPE = "type"         # "access" | "refresh"
_EXP = "exp"           # standard JWT expiry (unix timestamp)
_IAT = "iat"           # issued-at (unix timestamp)


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _encode(payload: dict) -> str:
    settings = get_settings()
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _decode(token: str) -> dict:
    """Decode and verify signature + expiry. Raises AuthenticationError on failure."""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        logger.warning("JWT decode failed", reason=str(exc))
        raise AuthenticationError("Invalid or expired token") from exc


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def create_access_token(subject: str, role: str) -> str:
    """
    Create a signed JWT access token.

    Args:
        subject: User UUID as a string.
        role:    UserRole value (e.g. "UNDERWRITER").

    Returns:
        Signed JWT string.
    """
    settings = get_settings()
    now = _now_utc()
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        _SUB: subject,
        _ROLE: role,
        _TYPE: "access",
        _IAT: int(now.timestamp()),
        _EXP: int(expire.timestamp()),
    }
    token = _encode(payload)
    logger.debug("Access token created", user_id=subject, role=role)
    return token


def create_refresh_token(subject: str) -> str:
    """
    Create a signed JWT refresh token (role NOT included — only used to
    obtain a new access token, not for authorization decisions).

    Args:
        subject: User UUID as a string.

    Returns:
        Signed JWT string.
    """
    settings = get_settings()
    now = _now_utc()
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        _SUB: subject,
        _TYPE: "refresh",
        _IAT: int(now.timestamp()),
        _EXP: int(expire.timestamp()),
    }
    token = _encode(payload)
    logger.debug("Refresh token created", user_id=subject)
    return token


def verify_access_token(token: str) -> dict:
    """
    Verify an access token and return its payload.

    Returns a dict with at minimum:
        {
            "sub":  "<user-uuid>",
            "role": "<UserRole>",
            "type": "access",
        }

    Raises:
        AuthenticationError: If the token is invalid, expired, or not an
                             access token.
    """
    payload = _decode(token)

    if payload.get(_TYPE) != "access":
        raise AuthenticationError("Token is not an access token")

    if not payload.get(_SUB):
        raise AuthenticationError("Token missing subject claim")

    return payload


def verify_refresh_token(token: str) -> dict:
    """
    Verify a refresh token and return its payload.

    Returns:
        {"sub": "<user-uuid>", "type": "refresh", ...}

    Raises:
        AuthenticationError: If the token is invalid, expired, or not a
                             refresh token.
    """
    payload = _decode(token)

    if payload.get(_TYPE) != "refresh":
        raise AuthenticationError("Token is not a refresh token")

    if not payload.get(_SUB):
        raise AuthenticationError("Token missing subject claim")

    return payload


def decode_token_type(token: str) -> Literal["access", "refresh"]:
    """
    Decode token (verifying signature) and return its type without
    enforcing which type it is. Useful for routing in refresh endpoints.
    """
    payload = _decode(token)
    token_type = payload.get(_TYPE)
    if token_type not in ("access", "refresh"):
        raise AuthenticationError("Token has unknown type")
    return token_type  # type: ignore[return-value]
