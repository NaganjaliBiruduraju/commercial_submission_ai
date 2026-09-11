"""
PDF parser — pdfplumber primary, PyMuPDF (fitz) fallback.

Strategy:
  1. Try pdfplumber first — best for text-based PDFs with tables.
     pdfplumber uses pdfminer under the hood and excels at table extraction.
  2. If pdfplumber yields < 50 avg chars/page, try PyMuPDF (fitz).
     PyMuPDF handles some PDFs that pdfplumber struggles with
     (e.g., unusual encodings, certain ACORD form renderings).
  3. If both yield minimal text, mark needs_ocr=True and return a
     skeleton ParsedDocument so Phase 5 (OCR) can handle it.
  4. If the PDF is password-protected, mark is_encrypted=True.

Table extraction (pdfplumber only):
  pdfplumber's table extraction is excellent for ACORD forms which use
  structured grids. PyMuPDF does not extract tables — we only use it
  for raw text recovery.
"""
from __future__ import annotations

import io
from typing import Any

from app.core.exceptions import DocumentParsingError
from app.ingestion.base_parser import BaseParser
from app.ingestion.models import ParsedDocument, ParsedPage, ParsedTable, ParserBackend


class PDFParser(BaseParser):
    """
    Parses PDF files using pdfplumber with PyMuPDF fallback.
    """

    def can_parse(self, mime_type: str, extension: str) -> bool:
        return mime_type == "application/pdf" or extension == "pdf"

    def _parse_bytes(
        self,
        file_bytes: bytes,
        document_id: str,
        original_filename: str,
        mime_type: str,
    ) -> ParsedDocument:
        result = ParsedDocument(
            document_id=document_id,
            original_filename=original_filename,
            mime_type=mime_type,
        )

        # --- Attempt 1: pdfplumber ---
        try:
            result = self._parse_with_pdfplumber(file_bytes, result)
        except Exception as exc:
            result.parse_warnings.append(
                f"pdfplumber failed: {type(exc).__name__}: {exc}"
            )

        # --- Attempt 2: PyMuPDF fallback if text is thin ---
        if result.is_encrypted:
            return result  # can't do better without password

        pages_text = [p.text for p in result.pages]
        if self._is_scanned_pdf(pages_text, max(len(pages_text), 1)):
            result.parse_warnings.append(
                "pdfplumber extracted minimal text — trying PyMuPDF"
            )
            result = self._parse_with_pymupdf(file_bytes, result)

        # --- Detect scanned PDF (Phase 5 will handle with OCR) ---
        pages_text = [p.text for p in result.pages]
        if result.pages and self._is_scanned_pdf(pages_text, len(result.pages)):
            result.needs_ocr = True
            result.parse_warnings.append(
                "Document appears to be a scanned image PDF. "
                "OCR processing required (Phase 5)."
            )

        return result

    # ------------------------------------------------------------------ #
    # pdfplumber implementation
    # ------------------------------------------------------------------ #

    def _parse_with_pdfplumber(
        self, file_bytes: bytes, result: ParsedDocument
    ) -> ParsedDocument:
        try:
            import pdfplumber
        except ImportError:
            result.parse_warnings.append("pdfplumber not installed")
            return result

        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                # Check for encryption
                if pdf.doc.is_encrypted:
                    result.is_encrypted = True
                    result.parse_warnings.append(
                        "PDF is encrypted/password-protected. Cannot extract text."
                    )
                    result.parser_backend = ParserBackend.PDFPLUMBER
                    result.parser_version = _pdfplumber_version()
                    return result

                # Metadata
                meta = pdf.metadata or {}
                result.metadata.update({
                    k: str(v) for k, v in meta.items()
                    if v and k in (
                        "Title", "Author", "Creator", "Producer",
                        "CreationDate", "ModDate", "Subject",
                    )
                })

                result.pages = []
                for i, page in enumerate(pdf.pages, start=1):
                    parsed_page = self._extract_pdfplumber_page(page, i, result)
                    result.pages.append(parsed_page)

        except Exception as exc:
            if "not encrypted" in str(exc).lower() or "encrypt" in str(exc).lower():
                result.is_encrypted = True
            raise DocumentParsingError(
                f"pdfplumber could not open PDF: {exc}",
                document_id=document_id if (document_id := result.document_id) else None,
            ) from exc

        result.parser_backend = ParserBackend.PDFPLUMBER
        result.parser_version = _pdfplumber_version()
        return result

    def _extract_pdfplumber_page(
        self, page: Any, page_number: int, result: ParsedDocument
    ) -> ParsedPage:
        """Extract text and tables from a single pdfplumber Page object."""
        parsed_page = ParsedPage(page_number=page_number, text="")
        warnings: list[str] = []

        # Extract text
        try:
            raw_text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            parsed_page.text = self._clean_text(raw_text)
        except Exception as exc:
            warnings.append(f"Page {page_number} text extraction failed: {exc}")

        # Extract tables
        try:
            tables = page.extract_tables() or []
            for t_idx, raw_table in enumerate(tables):
                if raw_table:
                    parsed_table = ParsedTable.from_raw(
                        page_number=page_number,
                        table_index=t_idx,
                        raw=raw_table,
                    )
                    parsed_page.tables.append(parsed_table)
        except Exception as exc:
            warnings.append(f"Page {page_number} table extraction failed: {exc}")

        # Page metadata
        parsed_page.metadata = {
            "width": float(page.width or 0),
            "height": float(page.height or 0),
        }

        for w in warnings:
            result.parse_warnings.append(w)

        return parsed_page

    # ------------------------------------------------------------------ #
    # PyMuPDF fallback
    # ------------------------------------------------------------------ #

    def _parse_with_pymupdf(
        self, file_bytes: bytes, result: ParsedDocument
    ) -> ParsedDocument:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            result.parse_warnings.append("PyMuPDF (fitz) not installed — cannot use fallback")
            return result

        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            result.parse_warnings.append(f"PyMuPDF failed to open PDF: {exc}")
            return result

        if doc.is_encrypted:
            result.is_encrypted = True
            return result

        # Rebuild pages with PyMuPDF text, preserving pdfplumber tables if any
        existing_tables: dict[int, list[ParsedTable]] = {
            p.page_number: p.tables for p in result.pages
        }

        new_pages: list[ParsedPage] = []
        for i in range(len(doc)):
            page_number = i + 1
            fitz_page = doc[i]
            try:
                raw_text = fitz_page.get_text("text") or ""
                clean = self._clean_text(raw_text)
            except Exception as exc:
                result.parse_warnings.append(
                    f"PyMuPDF page {page_number} text failed: {exc}"
                )
                clean = ""

            parsed_page = ParsedPage(
                page_number=page_number,
                text=clean,
                tables=existing_tables.get(page_number, []),
                metadata={"rotation": fitz_page.rotation},
            )
            new_pages.append(parsed_page)

        doc.close()
        result.pages = new_pages
        result.parser_backend = ParserBackend.PYMUPDF
        result.parser_version = _pymupdf_version()
        return result


# --------------------------------------------------------------------------- #
# Version helpers
# --------------------------------------------------------------------------- #

def _pdfplumber_version() -> str:
    try:
        import pdfplumber
        return getattr(pdfplumber, "__version__", "unknown")
    except ImportError:
        return "not-installed"


def _pymupdf_version() -> str:
    try:
        import fitz
        return getattr(fitz, "__version__", "unknown")
    except ImportError:
        return "not-installed"
