"""
Image parser — Pillow metadata only (Phase 4 stub).

Phase 4: Extract image metadata (dimensions, format, mode) and record
         that the file needs OCR. No text is extracted here.

Phase 5 (OCR): pytesseract will handle text extraction from images.
               The OCR service will call this parser first to validate
               the image, then run Tesseract on the output.

Accepted types: JPEG, PNG (and JPG as alias).

Why not extract text here?
  - Tesseract requires preprocessing (grayscale, denoising, deskew) that
    belongs in the dedicated OCR phase.
  - Running Tesseract inline in the parser would make this synchronous
    call very slow (5-30s per image) and would block the event loop.
  - The OCR phase (Phase 5) uses StageLogger to time and log OCR separately.
"""
from __future__ import annotations

import io
from typing import Any

from app.core.exceptions import DocumentParsingError
from app.ingestion.base_parser import BaseParser
from app.ingestion.models import ParsedDocument, ParsedPage, ParserBackend


class ImageParser(BaseParser):

    def can_parse(self, mime_type: str, extension: str) -> bool:
        return (
            mime_type in ("image/jpeg", "image/jpg", "image/png")
            or extension in ("jpg", "jpeg", "png")
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
            parser_backend=ParserBackend.PILLOW,
            parser_version=_pillow_version(),
            needs_ocr=True,  # always — images require OCR for text
        )

        try:
            from PIL import Image  # type: ignore[import]
        except ImportError:
            result.parse_warnings.append(
                "Pillow not installed. Image metadata extraction unavailable."
            )
            # Still create one empty page so downstream code doesn't break
            result.pages.append(
                ParsedPage(
                    page_number=1,
                    text="[Image file — OCR required (Phase 5)]",
                    metadata={"needs_ocr": True},
                )
            )
            return result

        try:
            img = Image.open(io.BytesIO(file_bytes))
            img_format = img.format or "UNKNOWN"
            width, height = img.size
            mode = img.mode  # e.g. "RGB", "L" (grayscale), "RGBA"
            dpi = img.info.get("dpi", None)

            # EXIF metadata (non-sensitive fields only)
            exif_data: dict[str, Any] = {}
            try:
                from PIL.ExifTags import TAGS
                raw_exif = img._getexif()  # type: ignore[attr-defined]
                if raw_exif:
                    safe_tags = {
                        "DateTime", "DateTimeOriginal", "Make", "Model",
                        "XResolution", "YResolution", "ResolutionUnit",
                        "Orientation", "ColorSpace",
                    }
                    exif_data = {
                        TAGS.get(k, str(k)): str(v)
                        for k, v in raw_exif.items()
                        if TAGS.get(k, str(k)) in safe_tags
                    }
            except Exception:
                pass

            result.metadata = {
                "format": img_format,
                "width_px": width,
                "height_px": height,
                "color_mode": mode,
                "dpi": str(dpi) if dpi else "unknown",
                **exif_data,
            }

            page_text = (
                f"[Image file: {original_filename}]\n"
                f"Format: {img_format} | Size: {width}×{height}px | Mode: {mode}\n"
                f"OCR text extraction required (Phase 5)."
            )

            result.pages.append(
                ParsedPage(
                    page_number=1,
                    text=page_text,
                    metadata={
                        "needs_ocr": True,
                        "width_px": width,
                        "height_px": height,
                        "color_mode": mode,
                    },
                )
            )
            img.close()

        except Exception as exc:
            raise DocumentParsingError(
                f"Pillow could not open image: {exc}",
                document_id=document_id,
            ) from exc

        result.parse_warnings.append(
            "Image file — text extraction deferred to OCR phase (Phase 5). "
            "No text content available until OCR is complete."
        )
        return result


def _pillow_version() -> str:
    try:
        from PIL import __version__ as pv  # type: ignore[import]
        return pv
    except ImportError:
        return "not-installed"
