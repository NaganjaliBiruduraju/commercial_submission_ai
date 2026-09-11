"""
OCR orchestrator — decides what needs OCR and merges results back into
a ParsedDocument.

This module is the single entry point for all OCR work. It handles:

  1. Images (JPG/PNG) — read the image bytes directly and OCR them.
  2. Scanned PDFs — render each page with PyMuPDF then OCR.
  3. Merge — replace the placeholder text in ParsedDocument.pages with
     the OCR-extracted text, update confidence metadata.

The orchestrator is synchronous internally (Tesseract is a subprocess).
The async wrapper run_ocr_async() dispatches it to the thread pool so
FastAPI's event loop is never blocked.

Merge strategy:
  - Each OCR page result maps to a ParsedDocument page by page_number.
  - If a page already has text (shouldn't happen for scanned docs but
    is possible for mixed PDFs), the OCR text is appended with a marker.
  - Page-level confidence is stored in ParsedPage.metadata["ocr_confidence"].
  - Document-level mean confidence is stored in ParsedDocument.metadata.
  - needs_ocr is set to False after successful OCR.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

from app.core.exceptions import DocumentParsingError, OCRError
from app.core.logging import get_logger
from app.ingestion.models import ParsedDocument, ParsedPage, ParserBackend
from app.ingestion.ocr_engine import OCRPageResult, is_tesseract_available, ocr_image
from app.ingestion.ocr_pdf import ocr_scanned_pdf

logger = get_logger(__name__)

# Shared thread pool for OCR (CPU-bound subprocess work)
# Smaller than the parse pool because OCR is much heavier per page
_OCR_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ocr")


# --------------------------------------------------------------------------- #
# Synchronous core
# --------------------------------------------------------------------------- #

def run_ocr_on_document(
    file_bytes: bytes,
    parsed_doc: ParsedDocument,
    lang: str = "eng",
) -> ParsedDocument:
    """
    Run OCR on a document that needs it and merge results into parsed_doc.

    This is synchronous — call via run_ocr_async() from async code.

    Args:
        file_bytes:  Raw file bytes of the original document.
        parsed_doc:  ParsedDocument from Phase 4 (may have empty pages).
        lang:        Tesseract language string (e.g. "eng", "eng+fra").

    Returns:
        Updated ParsedDocument with OCR text filled in.
        needs_ocr is set to False on success.

    Raises:
        OCRError:             Tesseract not available.
        DocumentParsingError: PDF rendering failure.
    """
    if not parsed_doc.needs_ocr:
        logger.debug(
            "Document does not need OCR — skipping",
            document_id=parsed_doc.document_id,
        )
        return parsed_doc

    if not is_tesseract_available():
        raise OCRError(
            "Tesseract is not installed. OCR cannot proceed. "
            "Install Tesseract and set TESSERACT_CMD if needed."
        )

    mime = parsed_doc.mime_type.lower()
    is_pdf = "pdf" in mime
    is_image = any(t in mime for t in ("jpeg", "jpg", "png", "tiff", "bmp"))

    if is_pdf:
        ocr_results = ocr_scanned_pdf(
            pdf_bytes=file_bytes,
            document_id=parsed_doc.document_id,
            lang=lang,
        )
    elif is_image:
        result = ocr_image(
            image_bytes=file_bytes,
            page_number=1,
            lang=lang,
            apply_preprocessing=True,
        )
        ocr_results = [result]
    else:
        parsed_doc.parse_warnings.append(
            f"OCR requested for unsupported MIME type: {parsed_doc.mime_type}. Skipped."
        )
        return parsed_doc

    if not ocr_results:
        parsed_doc.parse_warnings.append("OCR produced no results.")
        return parsed_doc

    _merge_ocr_results(parsed_doc, ocr_results)

    logger.info(
        "OCR complete",
        document_id=parsed_doc.document_id,
        pages_ocred=len(ocr_results),
        mean_confidence=parsed_doc.metadata.get("ocr_mean_confidence"),
    )

    return parsed_doc


def _merge_ocr_results(
    parsed_doc: ParsedDocument,
    ocr_results: list[OCRPageResult],
) -> None:
    """
    Merge OCRPageResult list into parsed_doc.pages in-place.

    Strategy:
      - Build a dict of existing pages by page_number for fast lookup.
      - For each OCR result, either update the existing page or create a new one.
      - Update full_text and metadata.
    """
    existing_pages: dict[int, ParsedPage] = {
        p.page_number: p for p in parsed_doc.pages
    }

    all_confidences: list[float] = []
    total_words = 0
    low_confidence_pages: list[int] = []

    for ocr_page in ocr_results:
        pn = ocr_page.page_number

        if pn in existing_pages:
            page = existing_pages[pn]
            # Append OCR text if page already had placeholder text
            if page.text.strip() and not page.text.startswith("[Image"):
                page.text = page.text + "\n\n[OCR TEXT]\n" + ocr_page.text
            else:
                page.text = ocr_page.text
            page.char_count = len(page.text)
        else:
            # New page (OCR found more pages than Phase 4 knew about)
            new_page = ParsedPage(
                page_number=pn,
                text=ocr_page.text,
                metadata={},
            )
            existing_pages[pn] = new_page
            parsed_doc.pages.append(new_page)

        # Store confidence in page metadata
        existing_pages[pn].metadata["ocr_confidence"] = round(ocr_page.mean_confidence, 1)
        existing_pages[pn].metadata["ocr_word_count"] = ocr_page.word_count
        existing_pages[pn].metadata["ocr_preprocessing"] = ocr_page.preprocessing_applied

        if ocr_page.mean_confidence >= 0:
            all_confidences.append(ocr_page.mean_confidence)
        if ocr_page.is_low_confidence:
            low_confidence_pages.append(pn)
        total_words += ocr_page.word_count

        for warning in ocr_page.warnings:
            parsed_doc.parse_warnings.append(warning)

    # Sort pages by page_number
    parsed_doc.pages.sort(key=lambda p: p.page_number)

    # Update document-level metadata
    mean_conf = (
        sum(all_confidences) / len(all_confidences) if all_confidences else -1.0
    )
    parsed_doc.metadata["ocr_mean_confidence"] = round(mean_conf, 1)
    parsed_doc.metadata["ocr_total_words"] = total_words
    parsed_doc.metadata["ocr_low_confidence_pages"] = low_confidence_pages
    parsed_doc.metadata["ocr_language"] = "eng"  # updated by caller if different

    if low_confidence_pages:
        parsed_doc.parse_warnings.append(
            f"Low OCR confidence on pages: {low_confidence_pages}. "
            "These pages may contain errors — flagged for human review."
        )

    # Rebuild full_text from updated pages
    parsed_doc.build_full_text()

    # Mark OCR as complete
    parsed_doc.needs_ocr = False
    parsed_doc.parser_backend = ParserBackend.PILLOW  # closest enum for OCR output
    parsed_doc.metadata["ocr_complete"] = True


# --------------------------------------------------------------------------- #
# Async wrapper
# --------------------------------------------------------------------------- #

async def run_ocr_async(
    file_bytes: bytes,
    parsed_doc: ParsedDocument,
    lang: str = "eng",
) -> ParsedDocument:
    """
    Async wrapper — runs OCR in the thread pool executor.

    Use this from FastAPI route handlers and async services.
    """
    loop = asyncio.get_event_loop()
    fn = partial(run_ocr_on_document, file_bytes, parsed_doc, lang)

    try:
        result = await loop.run_in_executor(_OCR_EXECUTOR, fn)
    except (OCRError, DocumentParsingError):
        raise
    except Exception as exc:
        raise OCRError(
            f"Unexpected OCR failure on document '{parsed_doc.original_filename}': {exc}"
        ) from exc

    return result


# --------------------------------------------------------------------------- #
# Utility
# --------------------------------------------------------------------------- #

def ocr_availability_info() -> dict:
    """
    Return a dict describing OCR availability for the health/status endpoint.
    """
    available = is_tesseract_available()
    info: dict = {"available": available}

    if available:
        try:
            import pytesseract
            info["version"] = str(pytesseract.get_tesseract_version())
            info["languages"] = pytesseract.get_languages(config="")
        except Exception:
            info["version"] = "unknown"
            info["languages"] = []
    else:
        info["reason"] = (
            "Tesseract not found. Set TESSERACT_CMD env var or install tesseract-ocr."
        )

    return info
