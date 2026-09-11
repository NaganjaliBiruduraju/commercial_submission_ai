"""
DOCX parser — python-docx.

Extracts:
  - Body paragraphs (preserving heading levels in metadata)
  - Tables (all rows and columns)
  - Core document properties (author, created, modified)

Design decisions:
  - We iterate paragraphs and tables in document order using the
    document body's XML children rather than .paragraphs + .tables
    separately. This preserves the spatial relationship between text
    and tables (a table between two paragraphs appears in order).
  - Heading paragraphs are prefixed with their level (##, ###) so
    the extraction phase can identify section boundaries.
  - Images embedded in DOCX are noted in parse_warnings — OCR of
    embedded images is deferred to Phase 5.
  - DOCX files produce a single "page" conceptually. We split on
    explicit page breaks where python-docx can detect them.
"""
from __future__ import annotations

import io
from typing import Any

from app.core.exceptions import DocumentParsingError
from app.ingestion.base_parser import BaseParser
from app.ingestion.models import ParsedDocument, ParsedPage, ParsedTable, ParserBackend


class DOCXParser(BaseParser):

    def can_parse(self, mime_type: str, extension: str) -> bool:
        return (
            "wordprocessingml" in mime_type
            or extension in ("docx", "doc")
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
            parser_backend=ParserBackend.PYTHON_DOCX,
            parser_version=_docx_version(),
        )

        try:
            from docx import Document as DocxDocument  # type: ignore[import]
            from docx.oxml.ns import qn  # type: ignore[import]
        except ImportError:
            result.parse_warnings.append(
                "python-docx not installed. DOCX parsing unavailable."
            )
            return result

        try:
            doc = DocxDocument(io.BytesIO(file_bytes))
        except Exception as exc:
            raise DocumentParsingError(
                f"python-docx could not open file: {exc}",
                document_id=document_id,
            ) from exc

        # --- Core properties ---
        try:
            props = doc.core_properties
            result.metadata = {
                k: str(getattr(props, k, "") or "")
                for k in ("author", "created", "modified", "title", "subject")
                if getattr(props, k, None)
            }
        except Exception:
            pass

        # Check for embedded images
        try:
            inline_shapes = doc.inline_shapes
            if inline_shapes:
                result.parse_warnings.append(
                    f"Document contains {len(inline_shapes)} embedded image(s). "
                    "Image text is not extracted (Phase 5 OCR handles this)."
                )
        except Exception:
            pass

        # --- Walk body in document order ---
        # We produce one ParsedPage per logical page break (or one page
        # if there are no page breaks).
        pages_text: list[list[str]] = [[]]
        pages_tables: list[list[ParsedTable]] = [[]]

        table_idx = 0

        try:
            body = doc.element.body
            for child in body:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

                if tag == "p":
                    # Paragraph
                    para_text = _extract_paragraph_text(child, doc)
                    if para_text is not None:
                        pages_text[-1].append(para_text)
                    # Page break detection
                    if _has_page_break(child):
                        pages_text.append([])
                        pages_tables.append([])

                elif tag == "tbl":
                    # Table
                    raw_table = _extract_table_raw(child, doc)
                    if raw_table:
                        parsed_table = ParsedTable.from_raw(
                            page_number=len(pages_text),
                            table_index=table_idx,
                            raw=raw_table,
                        )
                        pages_tables[-1].append(parsed_table)
                        table_idx += 1
        except Exception as exc:
            raise DocumentParsingError(
                f"Error walking DOCX body: {exc}",
                document_id=document_id,
            ) from exc

        # Build ParsedPage objects
        for i, (texts, tables) in enumerate(zip(pages_text, pages_tables), start=1):
            page_text = self._clean_text("\n".join(texts))
            result.pages.append(
                ParsedPage(
                    page_number=i,
                    text=page_text,
                    tables=tables,
                )
            )

        return result


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _extract_paragraph_text(para_elem: Any, doc: Any) -> str | None:
    """
    Extract text from a paragraph XML element.

    Returns None for empty paragraphs (we skip them in the output).
    Prefixes heading paragraphs with markdown-style markers so the
    extraction phase can detect section boundaries.
    """
    from docx.oxml.ns import qn  # type: ignore[import]
    from docx import Document as DocxDocument  # type: ignore[import]
    from docx.text.paragraph import Paragraph  # type: ignore[import]

    para = Paragraph(para_elem, doc)
    text = para.text.strip()

    if not text:
        return None

    style_name = (para.style.name or "").lower() if para.style else ""

    # Prefix headings so extraction can detect sections
    if "heading 1" in style_name:
        return f"# {text}"
    elif "heading 2" in style_name:
        return f"## {text}"
    elif "heading 3" in style_name:
        return f"### {text}"
    else:
        return text


def _has_page_break(para_elem: Any) -> bool:
    """Return True if this paragraph element contains a page break."""
    from docx.oxml.ns import qn  # type: ignore[import]
    for br in para_elem.iter(qn("w:br")):
        br_type = br.get(qn("w:type"), "")
        if br_type == "page":
            return True
    return False


def _extract_table_raw(tbl_elem: Any, doc: Any) -> list[list[str | None]]:
    """Extract a table as a list-of-lists from its XML element."""
    from docx.oxml.ns import qn  # type: ignore[import]
    from docx.table import Table  # type: ignore[import]

    try:
        table = Table(tbl_elem, doc)
        rows: list[list[str | None]] = []
        for row in table.rows:
            cell_texts = []
            for cell in row.cells:
                cell_texts.append(cell.text.strip() or None)
            rows.append(cell_texts)
        return rows
    except Exception:
        return []


def _docx_version() -> str:
    try:
        import docx
        return getattr(docx, "__version__", "unknown")
    except ImportError:
        return "not-installed"
