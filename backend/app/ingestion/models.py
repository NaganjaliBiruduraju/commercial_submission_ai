"""
Shared data models for the document parsing layer.

These are pure Python dataclasses / Pydantic models — no database or
FastAPI imports. Every parser returns a ParsedDocument; the processing
service then writes that result to the DB.

Key design decisions:
  - ParsedPage is the unit of text extraction: one per physical page.
  - ParsedTable captures tabular data with header + rows (list-of-dicts).
  - ParsedDocument aggregates all pages + tables + metadata for a single file.
  - needs_ocr signals that the PDF contained no selectable text and must be
    routed to the OCR phase (Phase 5).
  - All text is stored as plain Unicode — no HTML, no markdown.
  - parser_version is recorded for reproducibility: if we upgrade pdfplumber
    we can reprocess only documents parsed with the old version.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ParserBackend(str, Enum):
    """Which library actually produced the output."""
    PDFPLUMBER = "pdfplumber"
    PYMUPDF    = "pymupdf"
    PYTHON_DOCX = "python-docx"
    OPENPYXL   = "openpyxl"
    PANDAS_CSV = "pandas-csv"
    PILLOW     = "pillow"          # image — text extracted by OCR (Phase 5)
    UNKNOWN    = "unknown"


@dataclass
class ParsedPage:
    """
    Text content of a single page (or sheet / section for non-PDF formats).

    Fields:
        page_number:  1-based page index within the document.
        text:         Full extracted plain text for this page/sheet.
                      Empty string if no text was found.
        char_count:   len(text) — precomputed to avoid re-scanning.
        tables:       Tabular structures found on this page.
        metadata:     Parser-specific extras (e.g., rotation angle, DPI).
    """
    page_number: int
    text: str
    char_count: int = 0
    tables: list["ParsedTable"] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.char_count = len(self.text)


@dataclass
class ParsedTable:
    """
    A table extracted from a document page or spreadsheet.

    Fields:
        page_number:  Page/sheet the table was found on.
        table_index:  0-based index among tables on this page.
        headers:      Column headers (first row, or synthesised Col_0/Col_1/…).
        rows:         List of dicts mapping header → cell value (as string).
        raw_rows:     Original list-of-lists from the parser (preserved for
                      re-parsing if header extraction changes).
    """
    page_number: int
    table_index: int
    headers: list[str]
    rows: list[dict[str, str]]
    raw_rows: list[list[str | None]] = field(default_factory=list)

    @classmethod
    def from_raw(
        cls,
        page_number: int,
        table_index: int,
        raw: list[list[str | None]],
    ) -> "ParsedTable":
        """
        Build a ParsedTable from a raw list-of-lists.

        If the first row looks like headers (no None values, all non-empty
        after stripping) we use it; otherwise we synthesise Col_0, Col_1, …
        """
        if not raw:
            return cls(
                page_number=page_number,
                table_index=table_index,
                headers=[],
                rows=[],
                raw_rows=raw,
            )

        # Normalise cells — replace None with empty string
        normalised = [
            [str(cell).strip() if cell is not None else "" for cell in row]
            for row in raw
        ]

        # Determine header row
        first_row = normalised[0]
        data_rows = normalised[1:] if len(normalised) > 1 else []

        if first_row and all(first_row):
            headers = first_row
        else:
            headers = [f"Col_{i}" for i in range(len(first_row))]
            data_rows = normalised  # include first row as data

        # Pad short rows to match header length
        col_count = len(headers)
        rows = []
        for row in data_rows:
            padded = row + [""] * (col_count - len(row))
            rows.append(dict(zip(headers, padded[:col_count])))

        return cls(
            page_number=page_number,
            table_index=table_index,
            headers=headers,
            rows=rows,
            raw_rows=raw,
        )


@dataclass
class ParsedDocument:
    """
    Complete parsed representation of a single uploaded document.

    This is the output of every parser and the input to the extraction phase.

    Fields:
        document_id:      UUID string of the Document DB record (for correlation).
        original_filename: Original broker-supplied filename (display only).
        mime_type:        MIME type as validated at upload.
        page_count:       Total number of pages / sheets parsed.
        pages:            Ordered list of ParsedPage objects.
        full_text:        Concatenation of all page text (convenience field).
                          Separated by double newlines between pages.
        all_tables:       Flat list of all ParsedTable from all pages.
        needs_ocr:        True if the document appears to be a scanned image
                          PDF with no selectable text (triggers Phase 5 OCR).
        is_encrypted:     True if the PDF was password-protected and unreadable.
        parser_backend:   Which library produced this result.
        parser_version:   Library version string.
        parse_warnings:   Non-fatal issues encountered during parsing.
        metadata:         Document-level metadata (author, creation date, etc.)
    """
    document_id: str
    original_filename: str
    mime_type: str

    page_count: int = 0
    pages: list[ParsedPage] = field(default_factory=list)
    full_text: str = ""
    all_tables: list[ParsedTable] = field(default_factory=list)

    needs_ocr: bool = False
    is_encrypted: bool = False

    parser_backend: ParserBackend = ParserBackend.UNKNOWN
    parser_version: str = ""
    parse_warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def build_full_text(self) -> None:
        """
        Populate full_text and all_tables from pages list.
        Call after all pages have been added.
        """
        page_texts = [p.text for p in self.pages if p.text.strip()]
        self.full_text = "\n\n".join(page_texts)
        self.all_tables = [t for p in self.pages for t in p.tables]
        self.page_count = len(self.pages)

    def total_chars(self) -> int:
        return sum(p.char_count for p in self.pages)

    def is_empty(self) -> bool:
        """True if no text was extracted at all."""
        return self.total_chars() == 0

    def get_table_as_text(self, table: "ParsedTable") -> str:
        """Return a plain-text representation of a table (for LLM prompts)."""
        if not table.headers:
            return ""
        lines = [" | ".join(table.headers)]
        lines.append("-" * len(lines[0]))
        for row in table.rows:
            lines.append(" | ".join(row.get(h, "") for h in table.headers))
        return "\n".join(lines)

    def tables_as_text(self) -> str:
        """All tables concatenated as plain text."""
        parts = []
        for i, table in enumerate(self.all_tables):
            parts.append(f"[Table {i + 1} — Page {table.page_number}]")
            parts.append(self.get_table_as_text(table))
        return "\n\n".join(parts)
