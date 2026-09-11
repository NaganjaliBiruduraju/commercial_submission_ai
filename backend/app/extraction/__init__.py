"""
Extraction layer — structured field extraction from parsed documents.

Public API:
  extract_fields(parsed_doc, document_type, rag_context) → ExtractionOutput
  get_fields_for_type(doc_type)  → list[FieldDefinition]
  locate_citation(citation, parsed_doc) → EvidenceLocation
"""
from app.extraction.extractor import ExtractionOutput, ExtractedFieldResult, extract_fields
from app.extraction.field_definitions import (
    FieldDefinition,
    get_fields_for_type,
    get_required_fields,
    get_field_names,
)
from app.extraction.evidence_mapper import EvidenceLocation, locate_citation, map_all_citations

__all__ = [
    "ExtractionOutput",
    "ExtractedFieldResult",
    "extract_fields",
    "FieldDefinition",
    "get_fields_for_type",
    "get_required_fields",
    "get_field_names",
    "EvidenceLocation",
    "locate_citation",
    "map_all_citations",
]
