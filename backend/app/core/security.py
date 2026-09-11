"""
Password hashing and verification utilities.

Uses passlib with bcrypt backend.
Passwords are NEVER stored as plaintext — only as bcrypt hashes.
Bcrypt is chosen because:
  - It is deliberately slow (computational cost factor is configurable)
  - It is resistant to GPU-accelerated brute-force attacks
  - It includes a built-in salt (no salt management required)

The verify_password function uses a constant-time comparison to
prevent timing attacks.

Note: This module only handles password hashing.
JWT token creation/verification is in app.auth.jwt.
"""
from __future__ import annotations

from passlib.context import CryptContext

# ---------------------------------------------------------------------------
# Password context
# ---------------------------------------------------------------------------
# schemes: bcrypt is the active scheme. "deprecated=auto" ensures that
# if we ever change the scheme, old hashes are detected and can be re-hashed.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """
    Hash a plaintext password using bcrypt.

    Returns the hashed password string suitable for database storage.
    Never store or log the plain_password.

    Args:
        plain_password: The user's plaintext password

    Returns:
        bcrypt hash string (includes algorithm, cost, salt, and hash)
    """
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash.

    Uses constant-time comparison to prevent timing attacks.
    Returns True only if the password matches the hash exactly.

    Args:
        plain_password:  The password provided by the user at login
        hashed_password: The hash stored in the database

    Returns:
        True if the password matches, False otherwise
    """
    return _pwd_context.verify(plain_password, hashed_password)


def needs_rehash(hashed_password: str) -> bool:
    """
    Return True if the hash was created with a deprecated algorithm
    or lower cost factor.

    Call this after a successful login and re-hash if True.
    This enables transparent hash migration without forcing password resets.
    """
    return _pwd_context.needs_update(hashed_password)
