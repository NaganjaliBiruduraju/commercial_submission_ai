"""
PDF-to-image renderer for OCR of scanned PDFs.

When Phase 4 (PDFParser) detects a scanned PDF (needs_ocr=True), this
module renders each page to a raster image using PyMuPDF (fitz), then
passes each image to the OCR engine.

Why PyMuPDF for rendering?
  - It renders PDF pages to RGB bitmaps at arbitrary DPI with excellent
    fidelity to the original scan.
  - It handles password-protected PDFs (if we ever support decryption).
  - It is already a dependency (used as PDF fallback in Phase 4).

Rendering resolution:
  We render at 300 DPI (the Tesseract sweet spot for accuracy).
  300 DPI on an A4 page = 2480 × 3508 pixels ≈ 26 MB per page as RGB.
  Pages are processed one at a time and discarded after OCR to limit
  peak memory usage.

Max pages:
  We cap at MAX_PAGES_PER_PDF (200) to prevent abuse. Insurance
  submissions rarely exceed 50 pages; loss runs can be longer.
"""
from __future__ import annotations

import io
from typing import Generator

from app.core.exceptions import DocumentParsingError, OCRError
from app.core.logging import get_logger
from app.ingestion.ocr_engine import OCRPageResult, ocr_image

logger = get_logger(__name__)

RENDER_DPI = 300
MAX_PAGES_PER_PDF = 200
_ZOOM = RENDER_DPI / 72  # PDF points → pixels (72 pt/inch baseline)


def iter_pdf_page_images(
    pdf_bytes: bytes,
    document_id: str,
) -> Generator[tuple[int, bytes], None, None]:
    """
    Render each page of a PDF to PNG bytes at RENDER_DPI.

    Yields (page_number, png_bytes) tuples, 1-based page numbers.
    Stops after MAX_PAGES_PER_PDF pages.

    Raises:
        DocumentParsingError: If PyMuPDF cannot open the PDF.
        OCRError:             If PyMuPDF is not installed.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise OCRError(
            "PyMuPDF (fitz) is required for PDF OCR rendering. "
            "Install with: pip install PyMuPDF"
        )

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise DocumentParsingError(
            f"PyMuPDF could not open PDF for OCR rendering: {exc}",
            document_id=document_id,
        ) from exc

    total_pages = len(doc)
    if total_pages > MAX_PAGES_PER_PDF:
        logger.warning(
            "PDF exceeds OCR page limit — truncating",
            document_id=document_id,
            total_pages=total_pages,
            limit=MAX_PAGES_PER_PDF,
        )

    matrix = fitz.Matrix(_ZOOM, _ZOOM)  # scale matrix for target DPI

    try:
        for page_idx in range(min(total_pages, MAX_PAGES_PER_PDF)):
            page = doc[page_idx]
            page_number = page_idx + 1

            try:
                # Render to RGB pixmap
                pixmap = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False)
                # Convert to PNG bytes
                png_bytes = pixmap.tobytes("png")
                pixmap = None  # release memory immediately
                yield page_number, png_bytes

            except Exception as exc:
                logger.warning(
                    "Failed to render PDF page — skipping",
                    document_id=document_id,
                    page=page_number,
                    error=str(exc),
                )
                continue

    finally:
        doc.close()


def ocr_scanned_pdf(
    pdf_bytes: bytes,
    document_id: str,
    lang: str = "eng",
) -> list[OCRPageResult]:
    """
    OCR all pages of a scanned PDF.

    Renders each page to an image then runs OCR on it.
    This is synchronous — run in a thread pool from async callers.

    Args:
        pdf_bytes:    Raw PDF bytes.
        document_id:  For logging and error context.
        lang:         Tesseract language (default "eng").

    Returns:
        List of OCRPageResult, one per page rendered.
        Empty list if no pages were rendered.

    Raises:
        DocumentParsingError / OCRError on fatal failures.
    """
    results: list[OCRPageResult] = []

    for page_number, png_bytes in iter_pdf_page_images(pdf_bytes, document_id):
        try:
            page_result = ocr_image(
                image_bytes=png_bytes,
                page_number=page_number,
                lang=lang,
                apply_preprocessing=True,
            )
            results.append(page_result)

            logger.debug(
                "PDF page OCR done",
                document_id=document_id,
                page=page_number,
                word_count=page_result.word_count,
                confidence=round(page_result.mean_confidence, 1),
            )

        except OCRError as exc:
            # Log and continue — don't abort the whole document for one bad page
            logger.warning(
                "OCR failed on PDF page — skipping",
                document_id=document_id,
                page=page_number,
                error=str(exc),
            )
            from app.ingestion.ocr_engine import OCRPageResult as _OCR
            results.append(
                OCRPageResult(
                    page_number=page_number,
                    text="",
                    mean_confidence=-1.0,
                    word_count=0,
                    is_low_confidence=True,
                    preprocessing_applied=[],
                    warnings=[f"OCR failed: {exc}"],
                )
            )

    logger.info(
        "Scanned PDF OCR complete",
        document_id=document_id,
        pages_processed=len(results),
        avg_confidence=round(
            sum(r.mean_confidence for r in results if r.mean_confidence >= 0)
            / max(sum(1 for r in results if r.mean_confidence >= 0), 1),
            1,
        ),
    )

    return results
