"""
Evidence mapper — locates LLM source-text citations within the ParsedDocument.

The LLM returns a source_text string (a quote from the document) for each
extracted field. This module maps that quote back to:
  - page_number:  Which ParsedPage it was found on (1-based)
  - section:      The section heading immediately before the quote (if detectable)

Matching strategy:
  1. Exact substring match across all pages (fastest, most reliable).
  2. If no exact match, try case-insensitive match.
  3. If still no match, try a sliding-window fuzzy match using
     difflib.SequenceMatcher (handles minor OCR differences).
  4. If no match found, return page_number=None, section=None.

Why bother?
  Evidence records are what allow the UI to highlight the exact passage
  in the source document that supported each extracted value. Without this
  mapping, the UI can only show the raw quote without navigation.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Optional

from app.ingestion.models import ParsedDocument, ParsedPage
from app.core.logging import get_logger

logger = get_logger(__name__)

# Minimum similarity ratio for fuzzy match (0.0–1.0)
FUZZY_MIN_RATIO = 0.75
# Window size for fuzzy search (chars around the expected text)
FUZZY_WINDOW = 300


@dataclass
class EvidenceLocation:
    """Location of a citation within a ParsedDocument."""
    page_number: Optional[int]      # 1-based, or None if not found
    section: Optional[str]          # Section heading, or None
    matched_text: Optional[str]     # The actual matched text (may differ from citation for fuzzy)
    match_method: str               # "exact" | "case_insensitive" | "fuzzy" | "not_found"
    confidence: float               # 1.0 exact, 0.9 case-insensitive, <1.0 fuzzy, 0.0 not found


def locate_citation(
    citation: str,
    parsed_doc: ParsedDocument,
) -> EvidenceLocation:
    """
    Find where a citation string appears in a ParsedDocument.

    Args:
        citation:    The source_text returned by the LLM.
        parsed_doc:  The parsed document to search.

    Returns:
        EvidenceLocation with page_number and section if found.
    """
    if not citation or not citation.strip():
        return EvidenceLocation(
            page_number=None, section=None,
            matched_text=None, match_method="not_found", confidence=0.0,
        )

    citation_clean = citation.strip()

    # 1. Exact match
    for page in parsed_doc.pages:
        if citation_clean in page.text:
            section = _find_section_heading(citation_clean, page)
            return EvidenceLocation(
                page_number=page.page_number,
                section=section,
                matched_text=citation_clean,
                match_method="exact",
                confidence=1.0,
            )

    # 2. Case-insensitive match
    citation_lower = citation_clean.lower()
    for page in parsed_doc.pages:
        if citation_lower in page.text.lower():
            section = _find_section_heading(citation_clean, page)
            return EvidenceLocation(
                page_number=page.page_number,
                section=section,
                matched_text=citation_clean,
                match_method="case_insensitive",
                confidence=0.9,
            )

    # 3. Fuzzy match (for OCR noise)
    best = _fuzzy_search(citation_clean, parsed_doc.pages)
    if best is not None:
        page, matched, ratio = best
        section = _find_section_heading(matched, page)
        return EvidenceLocation(
            page_number=page.page_number,
            section=section,
            matched_text=matched,
            match_method="fuzzy",
            confidence=round(ratio, 3),
        )

    logger.debug(
        "Citation not located in document",
        citation_preview=citation_clean[:80],
        document_id=parsed_doc.document_id,
    )
    return EvidenceLocation(
        page_number=None, section=None,
        matched_text=None, match_method="not_found", confidence=0.0,
    )


def _find_section_heading(citation: str, page: ParsedPage) -> str | None:
    """
    Find the nearest heading line before the citation on the page.

    Looks for lines starting with # or ## (heading markers added by DOCX parser)
    or ALL-CAPS lines that look like section headers.
    """
    if not page.text:
        return None

    citation_pos = page.text.lower().find(citation.lower())
    if citation_pos == -1:
        return None

    # Look at the text before the citation position
    before = page.text[:citation_pos]
    lines = before.split("\n")

    # Walk backwards to find the nearest heading
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        # Markdown-style headings (from DOCX parser)
        if stripped.startswith("# ") or stripped.startswith("## ") or stripped.startswith("### "):
            return stripped.lstrip("#").strip()
        # ALL-CAPS line (potential section header, at least 4 chars)
        if len(stripped) >= 4 and stripped.isupper() and stripped.replace(" ", "").isalpha():
            return stripped
        # Stop after finding non-blank non-heading lines (too far back)
        if len(stripped) > 80:
            break

    return None


def _fuzzy_search(
    citation: str,
    pages: list[ParsedPage],
) -> tuple[ParsedPage, str, float] | None:
    """
    Search pages using difflib for approximate matches.

    Returns (page, matched_window, ratio) or None.
    Only searches if citation is >= 20 chars (short strings have too many
    accidental fuzzy matches).
    """
    if len(citation) < 20:
        return None

    best_ratio = 0.0
    best_result: tuple[ParsedPage, str, float] | None = None
    window_size = max(len(citation), FUZZY_WINDOW)

    for page in pages:
        text = page.text
        if not text:
            continue

        # Slide window across page text
        step = max(1, window_size // 4)
        for start in range(0, max(1, len(text) - window_size + 1), step):
            window = text[start: start + window_size]
            ratio = difflib.SequenceMatcher(None, citation, window).ratio()
            if ratio > best_ratio and ratio >= FUZZY_MIN_RATIO:
                best_ratio = ratio
                best_result = (page, window, ratio)

    return best_result


def map_all_citations(
    field_citations: dict[str, str],
    parsed_doc: ParsedDocument,
) -> dict[str, EvidenceLocation]:
    """
    Map a dict of {field_name: source_text} to EvidenceLocation for each.

    Args:
        field_citations: Mapping of field name → LLM citation string.
        parsed_doc:      The document to search.

    Returns:
        Dict of field name → EvidenceLocation.
    """
    return {
        field_name: locate_citation(citation, parsed_doc)
        for field_name, citation in field_citations.items()
        if citation
    }
