"""
CSV parser — pandas + csv stdlib fallback.

Extracts:
  - The entire CSV as a single ParsedTable.
  - A human-readable text representation of the first N rows.
  - Delimiter auto-detection via csv.Sniffer.
  - Encoding detection: tries UTF-8, then latin-1, then cp1252.

Design decisions:
  - pandas is the primary parser — it handles edge cases (quoted fields,
    embedded newlines, mixed types) much better than the stdlib csv module.
  - The stdlib csv fallback exists so the system still works if pandas
    is somehow unavailable.
  - We cap at MAX_ROWS (10 000) to prevent memory issues.
  - Dates and numbers are kept as strings — type inference is the
    extraction phase's job (Phase 8), not the parser's.
"""
from __future__ import annotations

import csv
import io
from typing import Any

from app.core.exceptions import DocumentParsingError
from app.ingestion.base_parser import BaseParser
from app.ingestion.models import ParsedDocument, ParsedPage, ParsedTable, ParserBackend

MAX_ROWS = 10_000
PREVIEW_ROWS = 100  # rows to include in page text preview
ENCODINGS_TO_TRY = ("utf-8-sig", "utf-8", "latin-1", "cp1252")


class CSVParser(BaseParser):

    def can_parse(self, mime_type: str, extension: str) -> bool:
        return (
            mime_type in ("text/csv", "text/plain", "application/csv")
            or extension == "csv"
        )

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
            parser_backend=ParserBackend.PANDAS_CSV,
            parser_version=_pandas_version(),
        )

        # Decode with encoding fallback
        text_content, encoding_used = _decode_bytes(file_bytes)
        if text_content is None:
            raise DocumentParsingError(
                "Could not decode CSV file with any supported encoding "
                f"({', '.join(ENCODINGS_TO_TRY)})",
                document_id=document_id,
            )
        result.metadata["encoding_detected"] = encoding_used

        # Detect delimiter
        delimiter = _sniff_delimiter(text_content)
        result.metadata["delimiter_detected"] = repr(delimiter)

        # Parse
        raw_rows, truncated = _parse_csv_content(text_content, delimiter)

        if truncated:
            result.parse_warnings.append(
                f"CSV truncated to {MAX_ROWS} rows. "
                f"Full file has more rows — consider splitting large CSVs."
            )

        if not raw_rows:
            result.parse_warnings.append("CSV file is empty or contains no data rows.")
            result.pages.append(ParsedPage(page_number=1, text="[Empty CSV]"))
            return result

        result.metadata["total_rows_parsed"] = len(raw_rows)
        result.metadata["column_count"] = len(raw_rows[0]) if raw_rows else 0

        # Build ParsedTable
        parsed_table = ParsedTable.from_raw(
            page_number=1,
            table_index=0,
            raw=raw_rows,
        )

        # Build page text: header + preview rows
        text_lines = [f"[CSV: {original_filename}]"]
        if parsed_table.headers:
            text_lines.append(" | ".join(parsed_table.headers))
            for row_dict in parsed_table.rows[:PREVIEW_ROWS]:
                text_lines.append(
                    " | ".join(row_dict.get(h, "") for h in parsed_table.headers)
                )
            if len(parsed_table.rows) > PREVIEW_ROWS:
                text_lines.append(
                    f"... ({len(parsed_table.rows) - PREVIEW_ROWS} more rows)"
                )

        result.pages.append(
            ParsedPage(
                page_number=1,
                text=self._clean_text("\n".join(text_lines)),
                tables=[parsed_table],
                metadata={
                    "row_count": len(parsed_table.rows),
                    "col_count": len(parsed_table.headers),
                    "delimiter": delimiter,
                    "encoding": encoding_used,
                },
            )
        )

        return result


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _decode_bytes(file_bytes: bytes) -> tuple[str | None, str]:
    """Try each encoding in order, return (text, encoding) or (None, '')."""
    for enc in ENCODINGS_TO_TRY:
        try:
            return file_bytes.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return None, ""


def _sniff_delimiter(text: str) -> str:
    """Use csv.Sniffer to detect the delimiter; default to comma."""
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t|;")
        return dialect.delimiter
    except csv.Error:
        return ","


def _parse_csv_content(
    text: str, delimiter: str
) -> tuple[list[list[str | None]], bool]:
    """
    Parse CSV text into raw list-of-lists.
    Returns (rows, truncated).
    Tries pandas first, falls back to stdlib csv.
    """
    # --- pandas primary ---
    try:
        import pandas as pd  # type: ignore[import]
        df = pd.read_csv(
            io.StringIO(text),
            sep=delimiter,
            dtype=str,           # keep everything as strings
            keep_default_na=False,  # don't convert "" to NaN
            nrows=MAX_ROWS + 1,  # +1 to detect truncation
            on_bad_lines="warn",
        )
        truncated = len(df) > MAX_ROWS
        df = df.head(MAX_ROWS)

        # Build raw rows: header row first, then data
        headers = list(df.columns)
        raw: list[list[str | None]] = [headers]
        for _, row in df.iterrows():
            raw.append([str(v) if v != "" else None for v in row])
        return raw, truncated

    except Exception:
        pass  # fall through to stdlib

    # --- stdlib csv fallback ---
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows: list[list[str | None]] = []
    for row in reader:
        if len(rows) >= MAX_ROWS + 1:
            return rows[:MAX_ROWS], True
        rows.append([cell or None for cell in row])
    return rows, False


def _pandas_version() -> str:
    try:
        import pandas as pd
        return pd.__version__
    except ImportError:
        return "not-installed"
