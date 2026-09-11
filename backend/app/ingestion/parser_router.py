"""
Parser router — selects the right parser for a given file and runs it.

This is the single entry point for all parsing. Callers never import
individual parsers directly; they call parse_document() here.

Responsibilities:
  1. Select the correct parser based on MIME type + extension.
  2. Run the parser synchronously in a thread pool executor so we don't
     block the async event loop (all parsers are sync libraries).
  3. Return a ParsedDocument (never raises on recoverable parse errors —
     those go into ParsedDocument.parse_warnings).

Parser precedence (first match wins):
  PDF → PDFParser
  DOCX/DOC → DOCXParser
  XLSX/XLS → XLSXParser
  CSV/TXT → CSVParser
  JPG/JPEG/PNG → ImageParser
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.exceptions import DocumentParsingError, UnsupportedFileTypeError
from app.core.logging import get_logger
from app.ingestion.base_parser import BaseParser
from app.ingestion.csv_parser import CSVParser
from app.ingestion.docx_parser import DOCXParser
from app.ingestion.image_parser import ImageParser
from app.ingestion.models import ParsedDocument
from app.ingestion.pdf_parser import PDFParser
from app.ingestion.xlsx_parser import XLSXParser

logger = get_logger(__name__)

# Singleton parser instances — parsers are stateless so one per type is fine
_PARSERS: list[BaseParser] = [
    PDFParser(),
    DOCXParser(),
    XLSXParser(),
    CSVParser(),
    ImageParser(),
]

# Thread pool for running sync parsers off the async event loop
# max_workers=4 keeps CPU usage bounded during concurrent uploads
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="parser")


def _select_parser(mime_type: str, extension: str) -> BaseParser:
    """
    Return the first parser that claims it can handle this file type.
    Raises UnsupportedFileTypeError if none match.
    """
    mime_lower = (mime_type or "").lower()
    ext_lower = (extension or "").lower().lstrip(".")

    for parser in _PARSERS:
        if parser.can_parse(mime_lower, ext_lower):
            return parser

    raise UnsupportedFileTypeError(f"{mime_type} (.{extension})")


def _extension_from_filename(filename: str) -> str:
    """Return lowercase extension without dot, or empty string."""
    return Path(filename).suffix.lstrip(".").lower()


def _run_parser_sync(
    parser: BaseParser,
    file_bytes: bytes,
    document_id: str,
    original_filename: str,
    mime_type: str,
) -> ParsedDocument:
    """Synchronous wrapper called inside the thread pool."""
    return parser.parse(
        file_bytes=file_bytes,
        document_id=document_id,
        original_filename=original_filename,
        mime_type=mime_type,
    )


async def parse_document(
    file_bytes: bytes,
    document_id: str,
    original_filename: str,
    mime_type: str,
) -> ParsedDocument:
    """
    Parse a document asynchronously.

    The actual parsing runs in a thread pool to avoid blocking the
    async event loop with CPU-bound / IO-bound sync library calls.

    Args:
        file_bytes:         Raw file content (already validated at upload).
        document_id:        UUID string of the Document DB record.
        original_filename:  Original broker-provided filename (display only).
        mime_type:          MIME type validated at upload time.

    Returns:
        ParsedDocument with all extracted content.

    Raises:
        UnsupportedFileTypeError: No parser registered for this type.
        DocumentParsingError:     Parser encountered an unrecoverable error.
    """
    extension = _extension_from_filename(original_filename)
    parser = _select_parser(mime_type, extension)

    logger.info(
        "Routing document to parser",
        parser=type(parser).__name__,
        document_id=document_id,
        filename=original_filename,
        mime_type=mime_type,
        size_bytes=len(file_bytes),
    )

    loop = asyncio.get_event_loop()
    fn = partial(
        _run_parser_sync,
        parser,
        file_bytes,
        document_id,
        original_filename,
        mime_type,
    )

    try:
        parsed_doc = await loop.run_in_executor(_EXECUTOR, fn)
    except (DocumentParsingError, UnsupportedFileTypeError):
        raise
    except Exception as exc:
        raise DocumentParsingError(
            f"Unexpected error during parsing of '{original_filename}': {exc}",
            document_id=document_id,
        ) from exc

    return parsed_doc


def get_supported_mime_types() -> list[str]:
    """Return the MIME types that at least one registered parser handles."""
    from app.core.constants import ALLOWED_MIME_TYPES
    return sorted(ALLOWED_MIME_TYPES)
