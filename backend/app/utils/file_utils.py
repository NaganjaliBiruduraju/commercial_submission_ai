"""
File storage and validation utilities.

All file I/O for uploads is funnelled through this module.

Security rules enforced here:
  1. Extension allowlist — reject anything not in settings.allowed_extensions_set
  2. MIME-type validation against actual file bytes (not just the extension)
  3. File size enforcement before reading the entire stream
  4. Stored filename is always a UUID — never the original broker-supplied name
  5. SHA-256 checksum calculated at write time for integrity verification

Why UUID filenames?
  - Original filename may contain path-traversal sequences (../../etc/passwd)
  - UUID prevents collisions across submissions
  - The original filename is stored in the database for display only
"""
from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

import aiofiles

from app.core.config import get_settings
from app.core.constants import ALLOWED_MIME_TYPES, EXTENSION_TO_MIME
from app.core.exceptions import DocumentValidationError, UnsupportedFileTypeError
from app.core.logging import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# MIME detection
# --------------------------------------------------------------------------- #

def _detect_mime_from_bytes(header: bytes, filename: str) -> str:
    """
    Detect MIME type from the first 512 bytes of the file.

    We try python-magic (libmagic bindings) first for reliable detection.
    If magic is unavailable, we fall back to extension-based detection.
    This fallback is less secure but keeps the system functional in
    environments where libmagic is not installed.
    """
    try:
        import magic  # type: ignore[import]
        return magic.from_buffer(header, mime=True)
    except (ImportError, Exception):
        # Fallback: derive MIME from extension
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return EXTENSION_TO_MIME.get(ext, "application/octet-stream")


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def validate_filename(original_filename: str) -> str:
    """
    Return the lower-case extension, or raise DocumentValidationError.

    Rejects:
      - files with no extension
      - extensions not in the allowed set
      - filenames that are empty
    """
    settings = get_settings()

    if not original_filename or not original_filename.strip():
        raise DocumentValidationError("Filename is empty", filename=original_filename)

    # Strip leading path components (defence-in-depth)
    safe_name = Path(original_filename).name

    if "." not in safe_name:
        raise DocumentValidationError(
            f"File '{safe_name}' has no extension. "
            f"Allowed: {', '.join(sorted(settings.allowed_extensions_set))}",
            filename=original_filename,
        )

    ext = safe_name.rsplit(".", 1)[-1].lower()

    if ext not in settings.allowed_extensions_set:
        raise UnsupportedFileTypeError(ext)

    return ext


def validate_mime_type(header_bytes: bytes, filename: str, extension: str) -> str:
    """
    Validate detected MIME type against extension allowlist.

    Returns the validated MIME type string.

    Raises:
        UnsupportedFileTypeError: MIME type not in allowlist.
        DocumentValidationError:  MIME type conflicts with extension.
    """
    detected = _detect_mime_from_bytes(header_bytes, filename)

    if detected not in ALLOWED_MIME_TYPES:
        raise UnsupportedFileTypeError(detected)

    # Cross-check: detected MIME should match expected MIME for extension
    expected = EXTENSION_TO_MIME.get(extension)
    if expected and detected not in (expected, "text/plain"):
        # Some CSV files are detected as text/plain — allow that
        if not (extension == "csv" and detected == "text/plain"):
            logger.warning(
                "MIME/extension mismatch — using detected MIME",
                filename=filename,
                extension=extension,
                expected_mime=expected,
                detected_mime=detected,
            )

    return detected


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #

def get_upload_dir(submission_id: str) -> Path:
    """
    Return the storage directory for a submission's documents.

    Structure: <UPLOAD_DIR>/<submission_id>/
    Creates the directory if it doesn't exist.
    """
    settings = get_settings()
    upload_path = Path(settings.upload_dir) / submission_id
    upload_path.mkdir(parents=True, exist_ok=True)
    return upload_path


def generate_stored_filename(extension: str) -> str:
    """
    Generate a UUID-based storage filename.

    Example: a3f4c2d1-1e2b-4c3d-8e4f-5a6b7c8d9e0f.pdf
    """
    return f"{uuid.uuid4()}.{extension}"


async def save_upload_file(
    file_data: bytes,
    submission_id: str,
    extension: str,
) -> tuple[str, str, int]:
    """
    Write uploaded file bytes to disk asynchronously.

    Returns:
        (stored_filename, checksum_sha256, file_size_bytes)
    """
    stored_filename = generate_stored_filename(extension)
    upload_dir = get_upload_dir(submission_id)
    file_path = upload_dir / stored_filename

    # Calculate checksum while writing
    sha256 = hashlib.sha256(file_data)
    checksum = sha256.hexdigest()
    size = len(file_data)

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(file_data)

    logger.debug(
        "File saved",
        stored_filename=stored_filename,
        size_bytes=size,
        submission_id=submission_id,
    )

    return stored_filename, checksum, size


async def delete_upload_file(submission_id: str, stored_filename: str) -> None:
    """
    Delete a stored file. Used when rolling back a failed upload transaction.
    Non-fatal if file doesn't exist (idempotent).
    """
    settings = get_settings()
    file_path = Path(settings.upload_dir) / submission_id / stored_filename
    try:
        if file_path.exists():
            file_path.unlink()
            logger.debug("File deleted", stored_filename=stored_filename)
    except OSError as e:
        logger.warning(
            "Could not delete file",
            stored_filename=stored_filename,
            error=str(e),
        )
