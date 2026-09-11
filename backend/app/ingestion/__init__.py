"""
Ingestion layer — file parsing and OCR pipeline.

Every uploaded file is treated as UNTRUSTED content.
Input guardrails are enforced before any processing begins.

Public API:
  parse_document(file_bytes, document_id, original_filename, mime_type)
      → ParsedDocument

  run_ocr_async(file_bytes, parsed_doc, lang) → ParsedDocument

  get_supported_mime_types() → list[str]
  ocr_availability_info() → dict
"""
from app.ingestion.models import ParsedDocument, ParsedPage, ParsedTable, ParserBackend
from app.ingestion.parser_router import parse_document, get_supported_mime_types
from app.ingestion.ocr_service import run_ocr_async, ocr_availability_info

__all__ = [
    "ParsedDocument",
    "ParsedPage",
    "ParsedTable",
    "ParserBackend",
    "parse_document",
    "get_supported_mime_types",
    "run_ocr_async",
    "ocr_availability_info",
]
