"""
JWT token creation and verification.

Uses python-jose with HS256 algorithm.
SECRET_KEY is loaded from environment — NEVER hard-coded.
Access tokens are short-lived (default 15 minutes).
Refresh tokens are longer-lived (default 7 days).

Implemented fully in Phase 2: Authentication and Users.
"""
from __future__ import annotations

# Phase 2 stub — implemented in Phase 2


def verify_access_token(token: str) -> dict:
    """
    Verify a JWT access token and return the decoded payload.
    Raises AuthenticationError if invalid or expired.
    Phase 2 implementation.
    """
    raise NotImplementedError("Phase 2: Authentication not yet implemented")


def create_access_token(subject: str, role: str) -> str:
    """
    Create a signed JWT access token.
    Phase 2 implementation.
    """
    raise NotImplementedError("Phase 2: Authentication not yet implemented")


def create_refresh_token(subject: str) -> str:
    """
    Create a signed JWT refresh token.
    Phase 2 implementation.
    """
    raise NotImplementedError("Phase 2: Authentication not yet implemented")
