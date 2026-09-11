"""
OCR engine — Tesseract wrapper with image preprocessing.

Responsibilities:
  1. Image preprocessing (grayscale, denoising, deskew, thresholding) to
     improve Tesseract accuracy on insurance documents (often low-quality
     scans with stamps, handwriting noise, skewed pages).
  2. Single-image OCR via pytesseract with confidence extraction.
  3. Per-word confidence scoring — returns both the raw text and a
     mean confidence score (0–100) so the extraction phase can flag
     low-confidence fields for human review.

Preprocessing pipeline (applied in order):
  1. Convert to grayscale (required by most Tesseract modes)
  2. Upscale if DPI < 150 (Tesseract performs best at 300 DPI)
  3. Adaptive threshold (Otsu's binarisation) — handles uneven lighting
  4. Deskew — correct page rotation up to ±10 degrees
  5. Light denoising (median blur) — removes scanner dust/noise

Why pytesseract and not a cloud OCR service?
  - No PII leaves the system (insurance docs contain SSNs, financials, etc.)
  - No per-page cost
  - Sufficient accuracy for typed ACORD forms (typically >95% character accuracy)
  - Tesseract 5 (LSTM) significantly outperforms v4 for document text

Tesseract must be installed separately:
  Windows: https://github.com/UB-Mannheim/tesseract/wiki
  Linux:   apt-get install tesseract-ocr
  Mac:     brew install tesseract

Set TESSERACT_CMD env var if tesseract is not on PATH.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.core.exceptions import OCRError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Tesseract page-segmentation modes relevant to insurance documents
# PSM 3  = fully automatic (default) — good for mixed-layout pages
# PSM 6  = uniform block of text — good for dense paragraphs
# PSM 11 = sparse text — good for forms with scattered fields
_DEFAULT_PSM = 3
_FORM_PSM = 6

# Minimum mean confidence threshold below which we flag low quality
LOW_CONFIDENCE_THRESHOLD = 60.0

# Target DPI for OCR — upscale images below this
TARGET_DPI = 300
MIN_DPI_FOR_UPSCALE = 150


@dataclass
class OCRPageResult:
    """
    Result of OCR on a single page/image.

    Fields:
        page_number:      1-based page index.
        text:             Extracted plain text.
        mean_confidence:  Average word-level confidence 0–100.
                          -1 means confidence data was unavailable.
        word_count:       Number of words detected.
        is_low_confidence: True if mean_confidence < LOW_CONFIDENCE_THRESHOLD.
        preprocessing_applied: List of preprocessing steps that were run.
        warnings:         Non-fatal issues encountered.
    """
    page_number: int
    text: str
    mean_confidence: float
    word_count: int
    is_low_confidence: bool
    preprocessing_applied: list[str]
    warnings: list[str]


def ocr_image(
    image_bytes: bytes,
    page_number: int,
    lang: str = "eng",
    psm: int = _DEFAULT_PSM,
    apply_preprocessing: bool = True,
) -> OCRPageResult:
    """
    Run OCR on raw image bytes (JPEG, PNG, TIFF, BMP).

    This is a synchronous function — call from a thread pool executor.

    Args:
        image_bytes:         Raw image bytes.
        page_number:         1-based page number (for logging/result).
        lang:                Tesseract language code (default "eng").
                             Use "eng+fra" for multi-language docs.
        psm:                 Tesseract page segmentation mode.
        apply_preprocessing: Set False to skip preprocessing (faster,
                             lower accuracy on low-quality scans).

    Returns:
        OCRPageResult with extracted text and confidence metrics.

    Raises:
        OCRError: If Tesseract is not installed or fails fatally.
    """
    _check_tesseract()

    import pytesseract  # type: ignore[import]
    from PIL import Image
    import io

    warnings: list[str] = []
    preprocessing_applied: list[str] = []

    # Load image
    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception as exc:
        raise OCRError(f"Could not open image for OCR: {exc}") from exc

    # Preprocessing
    if apply_preprocessing:
        img, preprocessing_applied, prep_warnings = _preprocess_image(img)
        warnings.extend(prep_warnings)

    # Run Tesseract — get detailed output with per-word confidence
    try:
        config = f"--psm {psm} --oem 3"  # oem 3 = LSTM + legacy
        tsv_data = pytesseract.image_to_data(
            img,
            lang=lang,
            config=config,
            output_type=pytesseract.Output.DICT,
        )
    except pytesseract.TesseractNotFoundError as exc:
        raise OCRError(
            "Tesseract not found. Install from https://github.com/UB-Mannheim/tesseract/wiki"
        ) from exc
    except Exception as exc:
        raise OCRError(f"Tesseract failed on page {page_number}: {exc}") from exc

    # Extract text and confidence
    text_parts: list[str] = []
    confidences: list[float] = []

    n_boxes = len(tsv_data["text"])
    for i in range(n_boxes):
        conf = int(tsv_data["conf"][i])
        word = str(tsv_data["text"][i]).strip()
        if conf > 0 and word:  # conf=-1 means non-word (line break markers)
            text_parts.append(word)
            confidences.append(float(conf))

        # Insert newlines at line/block boundaries
        level = int(tsv_data["level"][i])
        if level in (3, 4) and i > 0:  # block or paragraph boundary
            if text_parts and text_parts[-1] != "\n":
                text_parts.append("\n")

    raw_text = " ".join(
        part if part == "\n" else part
        for part in text_parts
    ).strip()

    # Clean up excessive whitespace
    import re
    clean_text = re.sub(r" {2,}", " ", raw_text)
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)

    mean_conf = sum(confidences) / len(confidences) if confidences else -1.0
    word_count = len(confidences)
    is_low = mean_conf >= 0 and mean_conf < LOW_CONFIDENCE_THRESHOLD

    if is_low:
        warnings.append(
            f"Low OCR confidence on page {page_number}: "
            f"{mean_conf:.1f}% (threshold {LOW_CONFIDENCE_THRESHOLD}%). "
            "Text may contain errors — human review recommended."
        )

    if word_count == 0:
        warnings.append(
            f"No text detected on page {page_number}. "
            "Page may be blank, an image without text, or require better scan quality."
        )

    logger.debug(
        "OCR page complete",
        page=page_number,
        word_count=word_count,
        mean_confidence=round(mean_conf, 1),
        preprocessing=preprocessing_applied,
    )

    return OCRPageResult(
        page_number=page_number,
        text=clean_text,
        mean_confidence=mean_conf,
        word_count=word_count,
        is_low_confidence=is_low,
        preprocessing_applied=preprocessing_applied,
        warnings=warnings,
    )


# --------------------------------------------------------------------------- #
# Preprocessing
# --------------------------------------------------------------------------- #

def _preprocess_image(
    img: Any,
) -> tuple[Any, list[str], list[str]]:
    """
    Apply preprocessing pipeline to improve OCR accuracy.

    Returns (processed_image, steps_applied, warnings).
    Steps are applied only when they're likely to help — we check
    image properties first to avoid degrading already-clean images.
    """
    import numpy as np
    from PIL import Image, ImageFilter

    steps: list[str] = []
    warnings: list[str] = []

    try:
        # 1. Convert to grayscale
        if img.mode != "L":
            img = img.convert("L")
            steps.append("grayscale")

        # 2. Upscale if too small for Tesseract
        dpi = img.info.get("dpi", (72, 72))
        effective_dpi = dpi[0] if isinstance(dpi, tuple) else dpi
        if effective_dpi and effective_dpi < MIN_DPI_FOR_UPSCALE:
            scale = TARGET_DPI / effective_dpi
            new_w = int(img.width * scale)
            new_h = int(img.height * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            steps.append(f"upscale_x{scale:.1f}")
        elif img.width < 1000:
            # Upscale small images regardless of reported DPI
            scale = 2.0
            img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
            steps.append("upscale_x2_small_image")

        # 3. Deskew (correct rotation)
        img, deskew_angle = _deskew(img)
        if abs(deskew_angle) > 0.5:
            steps.append(f"deskew_{deskew_angle:.1f}deg")

        # 4. Adaptive thresholding (Otsu binarisation)
        arr = np.array(img)
        threshold = _otsu_threshold(arr)
        binary = (arr > threshold).astype(np.uint8) * 255
        img = Image.fromarray(binary)
        steps.append("otsu_threshold")

        # 5. Light denoising (median filter)
        img = img.filter(ImageFilter.MedianFilter(size=3))
        steps.append("median_denoise")

    except Exception as exc:
        warnings.append(f"Preprocessing step failed (using original image): {exc}")

    return img, steps, warnings


def _otsu_threshold(gray_array: Any) -> int:
    """
    Compute Otsu's optimal binarisation threshold.
    Falls back to 128 if numpy histogram fails.
    """
    try:
        import numpy as np
        hist, bin_edges = np.histogram(gray_array.flatten(), bins=256, range=(0, 256))
        hist = hist.astype(float)
        total = hist.sum()
        if total == 0:
            return 128

        sum_total = np.dot(np.arange(256), hist)
        sum_b = 0.0
        w_b = 0.0
        max_var = 0.0
        threshold = 128

        for i in range(256):
            w_b += hist[i]
            if w_b == 0:
                continue
            w_f = total - w_b
            if w_f == 0:
                break
            sum_b += i * hist[i]
            mean_b = sum_b / w_b
            mean_f = (sum_total - sum_b) / w_f
            var_between = w_b * w_f * (mean_b - mean_f) ** 2
            if var_between > max_var:
                max_var = var_between
                threshold = i

        return threshold
    except Exception:
        return 128


def _deskew(img: Any) -> tuple[Any, float]:
    """
    Detect and correct page skew using projection profile analysis.
    Only corrects angles within ±10 degrees to avoid mis-rotation.
    Returns (corrected_image, angle_degrees).
    """
    try:
        import numpy as np
        from PIL import Image

        arr = np.array(img)
        # Binary: white text on black (invert for projection)
        binary = arr < 128  # True where dark pixels (text)

        best_angle = 0.0
        best_score = -1.0

        # Search over small angles
        for angle in range(-10, 11):
            from PIL import Image as PILImage
            rotated = PILImage.fromarray(arr).rotate(angle, expand=False, fillcolor=255)
            rot_arr = np.array(rotated) < 128
            # Projection profile: sum of dark pixels per row
            projection = rot_arr.sum(axis=1).astype(float)
            # Score: variance of projection (high variance = well-aligned text lines)
            score = float(projection.var())
            if score > best_score:
                best_score = score
                best_angle = float(angle)

        if abs(best_angle) > 0.5:
            img = img.rotate(best_angle, expand=False, fillcolor=255)

        return img, best_angle

    except Exception:
        return img, 0.0


# --------------------------------------------------------------------------- #
# Tesseract availability check
# --------------------------------------------------------------------------- #

def _check_tesseract() -> None:
    """
    Verify Tesseract is accessible. Raises OCRError if not.
    Reads TESSERACT_CMD env var to support non-default install paths.
    """
    import pytesseract  # type: ignore[import]

    custom_cmd = os.getenv("TESSERACT_CMD")
    if custom_cmd:
        pytesseract.pytesseract.tesseract_cmd = custom_cmd

    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        raise OCRError(
            "Tesseract OCR is not installed or not on PATH. "
            "Windows: https://github.com/UB-Mannheim/tesseract/wiki  "
            "Linux: apt-get install tesseract-ocr  "
            "Mac: brew install tesseract  "
            "Set TESSERACT_CMD=/path/to/tesseract if installed in non-default location."
        )
    except Exception as exc:
        raise OCRError(f"Tesseract check failed: {exc}") from exc


def is_tesseract_available() -> bool:
    """Return True if Tesseract is installed and reachable. Does not raise."""
    try:
        _check_tesseract()
        return True
    except OCRError:
        return False
