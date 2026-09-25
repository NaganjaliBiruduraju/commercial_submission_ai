"""
Extraction layer — prompt-driven field extraction from parsed documents.

Public API:
  extract_with_prompt(parsed_doc, prompt) → ExtractionOutput
  extract_with_default_prompt(parsed_doc, doc_type, rag_context) → ExtractionOutput
"""
from app.extraction.extractor import (
    ExtractionOutput,
    extract_with_prompt,
    extract_with_default_prompt,
)
from app.extraction.field_definitions import (
    FieldDefinition,
    get_fields_for_type,
    get_required_fields,
)

__all__ = [
    "ExtractionOutput",
    "extract_with_prompt",
    "extract_with_default_prompt",
    "FieldDefinition",
    "get_fields_for_type",
    "get_required_fields",
]
