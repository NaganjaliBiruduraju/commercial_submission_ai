"""
Ingestion layer — file parsing pipeline.

Every uploaded file is treated as UNTRUSTED content.
Input guardrails are enforced before any processing begins.

Public API:
  parse_document(file_bytes, document_id, original_filename, mime_type)
      → ParsedDocument

  get_supported_mime_types() → list[str]
"""
from app.ingestion.models import ParsedDocument, ParsedPage, ParsedTable, ParserBackend
from app.ingestion.parser_router import parse_document, get_supported_mime_types

__all__ = [
    "ParsedDocument",
    "ParsedPage",
    "ParsedTable",
    "ParserBackend",
    "parse_document",
    "get_supported_mime_types",
]
