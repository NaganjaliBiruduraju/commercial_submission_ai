"""
Abstract base class for all document parsers.

Every format-specific parser inherits from BaseParser and implements:
  - can_parse(mime_type, extension) → bool
  - parse(file_bytes, document_id, original_filename) → ParsedDocument

Design decisions:
  - Parsers receive raw bytes, NOT file paths. This keeps them stateless and
    testable without a real filesystem.
  - The parse() method MUST NOT raise on recoverable errors. It should
    populate parse_warnings and return a best-effort ParsedDocument.
    Only truly unrecoverable errors (e.g., corrupted file magic bytes that
    prevent any parsing) should raise DocumentParsingError.
  - Parsers are synchronous internally (pdfplumber/python-docx are sync libs).
    The processing service calls them via asyncio.get_event_loop().run_in_executor
    to avoid blocking the event loop.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.ingestion.models import ParsedDocument
from app.core.logging import get_logger

logger = get_logger(__name__)


class BaseParser(ABC):
    """
    Abstract document parser.

    Subclasses must implement can_parse() and _parse_bytes().
    """

    @abstractmethod
    def can_parse(self, mime_type: str, extension: str) -> bool:
        """
        Return True if this parser handles the given MIME type and extension.

        Both arguments are lowercase. Called by the parser router to select
        the right parser for an uploaded document.
        """
        ...

    def parse(
        self,
        file_bytes: bytes,
        document_id: str,
        original_filename: str,
        mime_type: str,
    ) -> ParsedDocument:
        """
        Parse file bytes and return a ParsedDocument.

        This is the public entry point. It wraps _parse_bytes() with
        logging and error handling so subclasses only need to implement
        the core parsing logic.
        """
        from app.core.logging import StageLogger
        from app.core.constants import ProcessingStage
        import asyncio

        logger.info(
            "Parser started",
            parser=type(self).__name__,
            filename=original_filename,
            document_id=document_id,
            size_bytes=len(file_bytes),
        )

        try:
            result = self._parse_bytes(
                file_bytes=file_bytes,
                document_id=document_id,
                original_filename=original_filename,
                mime_type=mime_type,
            )
            result.build_full_text()

            logger.info(
                "Parser completed",
                parser=type(self).__name__,
                document_id=document_id,
                page_count=result.page_count,
                char_count=result.total_chars(),
                table_count=len(result.all_tables),
                needs_ocr=result.needs_ocr,
                warnings=len(result.parse_warnings),
            )
            return result

        except Exception as exc:
            logger.error(
                "Parser failed",
                parser=type(self).__name__,
                document_id=document_id,
                filename=original_filename,
                error=str(exc),
                exc_info=True,
            )
            raise

    @abstractmethod
    def _parse_bytes(
        self,
        file_bytes: bytes,
        document_id: str,
        original_filename: str,
        mime_type: str,
    ) -> ParsedDocument:
        """
        Core parsing implementation.

        Must return a ParsedDocument with pages populated.
        Do NOT call build_full_text() here — the base parse() does that.

        For recoverable issues (e.g., a page with no text), add to
        result.parse_warnings instead of raising.
        """
        ...

    # ------------------------------------------------------------------ #
    # Helpers available to all subclasses
    # ------------------------------------------------------------------ #

    @staticmethod
    def _clean_text(text: str | None) -> str:
        """
        Normalise extracted text:
          - Replace None with ""
          - Collapse runs of 3+ blank lines to 2
          - Strip trailing whitespace from each line
          - Ensure single trailing newline
        """
        if not text:
            return ""
        lines = text.splitlines()
        cleaned: list[str] = []
        blank_run = 0
        for line in lines:
            stripped = line.rstrip()
            if not stripped:
                blank_run += 1
                if blank_run <= 2:
                    cleaned.append("")
            else:
                blank_run = 0
                cleaned.append(stripped)
        return "\n".join(cleaned).strip()

    @staticmethod
    def _is_scanned_pdf(pages_text: list[str], page_count: int) -> bool:
        """
        Heuristic to detect scanned / image-only PDFs.

        A PDF is considered scanned if:
          - It has at least one page, AND
          - The average character count per page is below 50
            (legitimate text PDFs typically have hundreds of chars/page)
        """
        if page_count == 0:
            return False
        total_chars = sum(len(t) for t in pages_text)
        avg_chars = total_chars / page_count
        return avg_chars < 50
