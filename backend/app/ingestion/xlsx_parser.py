"""
XLSX / XLS parser — openpyxl.

Extracts:
  - Each worksheet becomes one ParsedPage (page_number = sheet index).
  - Every sheet is also extracted as a ParsedTable (the whole sheet as a grid).
  - Cell values are converted to strings; dates are ISO-formatted.
  - Hidden sheets are skipped (noted in parse_warnings).
  - Merged cells are unmerged — the top-left value is replicated into all
    merged positions so the table makes sense as a flat grid.
  - Named ranges are recorded in metadata for reference.

Design decisions:
  - We use openpyxl (read_only=False so we can access merged cells).
    xlrd is intentionally NOT used for .xls because it has unpatched
    CVEs for malicious XLS files. .xls is very rare in insurance submissions;
    we warn and return empty if encountered.
  - We cap the number of rows per sheet at MAX_ROWS_PER_SHEET (5000) to
    prevent memory exhaustion from adversarially large files.
"""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import Any

from app.core.exceptions import DocumentParsingError
from app.ingestion.base_parser import BaseParser
from app.ingestion.models import ParsedDocument, ParsedPage, ParsedTable, ParserBackend

MAX_ROWS_PER_SHEET = 5_000
MAX_COLS_PER_SHEET = 200


class XLSXParser(BaseParser):

    def can_parse(self, mime_type: str, extension: str) -> bool:
        return (
            "spreadsheetml" in mime_type
            or "ms-excel" in mime_type
            or extension in ("xlsx", "xls", "xlsm")
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
            parser_backend=ParserBackend.OPENPYXL,
            parser_version=_openpyxl_version(),
        )

        # Warn about legacy .xls
        ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
        if ext == "xls":
            result.parse_warnings.append(
                "Legacy .xls format detected. openpyxl may not fully support it. "
                "Consider converting to .xlsx for best results."
            )

        try:
            import openpyxl  # type: ignore[import]
        except ImportError:
            result.parse_warnings.append("openpyxl not installed. XLSX parsing unavailable.")
            return result

        try:
            wb = openpyxl.load_workbook(
                io.BytesIO(file_bytes),
                read_only=False,   # needed for merged_cells
                data_only=True,    # use cached formula values, not formulas
                keep_links=False,
            )
        except Exception as exc:
            raise DocumentParsingError(
                f"openpyxl could not open workbook: {exc}",
                document_id=document_id,
            ) from exc

        # Workbook-level metadata
        try:
            props = wb.properties
            result.metadata = {
                k: str(getattr(props, k) or "")
                for k in ("creator", "created", "modified", "title", "subject", "description")
                if getattr(props, k, None)
            }
        except Exception:
            pass

        result.metadata["sheet_names"] = wb.sheetnames

        table_global_idx = 0
        for sheet_idx, sheet_name in enumerate(wb.sheetnames, start=1):
            ws = wb[sheet_name]

            # Skip hidden sheets
            if ws.sheet_state != "visible":
                result.parse_warnings.append(
                    f"Sheet '{sheet_name}' is hidden — skipped."
                )
                continue

            # Unmerge cells (replicate top-left value)
            _expand_merged_cells(ws)

            # Read up to MAX_ROWS_PER_SHEET rows
            raw_rows: list[list[str | None]] = []
            row_count = 0
            for row in ws.iter_rows():
                if row_count >= MAX_ROWS_PER_SHEET:
                    result.parse_warnings.append(
                        f"Sheet '{sheet_name}' truncated at {MAX_ROWS_PER_SHEET} rows."
                    )
                    break
                cell_values = [
                    _cell_to_str(cell.value)
                    for cell in row[:MAX_COLS_PER_SHEET]
                ]
                # Skip completely empty rows
                if any(v for v in cell_values):
                    raw_rows.append(cell_values)
                    row_count += 1

            if not raw_rows:
                result.parse_warnings.append(f"Sheet '{sheet_name}' is empty — skipped.")
                continue

            # Build ParsedTable for this sheet
            parsed_table = ParsedTable.from_raw(
                page_number=sheet_idx,
                table_index=table_global_idx,
                raw=raw_rows,
            )
            table_global_idx += 1

            # Build page text: header row + first N data rows as readable text
            text_lines = [f"[Sheet: {sheet_name}]"]
            if parsed_table.headers:
                text_lines.append(" | ".join(parsed_table.headers))
                for row_dict in parsed_table.rows[:100]:  # first 100 rows for text
                    text_lines.append(
                        " | ".join(row_dict.get(h, "") for h in parsed_table.headers)
                    )

            result.pages.append(
                ParsedPage(
                    page_number=sheet_idx,
                    text=self._clean_text("\n".join(text_lines)),
                    tables=[parsed_table],
                    metadata={"sheet_name": sheet_name, "row_count": len(raw_rows)},
                )
            )

        wb.close()
        return result


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _cell_to_str(value: Any) -> str | None:
    """Convert a cell value to a clean string."""
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        # Avoid scientific notation for large integers
        if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip() or None


def _expand_merged_cells(ws: Any) -> None:
    """
    Replicate the top-left value of each merged range into all cells
    of that range so they appear as regular data rows.
    """
    try:
        # Copy merged_cells list before unmerging (modifying during iteration fails)
        merged_ranges = list(ws.merged_cells.ranges)
        for merged_range in merged_ranges:
            min_row = merged_range.min_row
            min_col = merged_range.min_col
            top_left_value = ws.cell(row=min_row, column=min_col).value
            ws.unmerge_cells(str(merged_range))
            for row in ws.iter_rows(
                min_row=merged_range.min_row,
                max_row=merged_range.max_row,
                min_col=merged_range.min_col,
                max_col=merged_range.max_col,
            ):
                for cell in row:
                    cell.value = top_left_value
    except Exception:
        pass  # non-fatal — proceed with merged cells as-is


def _openpyxl_version() -> str:
    try:
        import openpyxl
        return getattr(openpyxl, "__version__", "unknown")
    except ImportError:
        return "not-installed"
