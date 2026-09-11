"""
LLM extraction engine — extracts structured fields from a ParsedDocument.

Flow:
  1. Look up field definitions for the document's classified type.
  2. Build a prompt (via prompt_builder) with the document text + field list.
  3. Call the LLM via llm_client.complete_json().
  4. Parse the JSON response into a list of ExtractionResult objects.
  5. Map each source_text citation to a page/section via evidence_mapper.
  6. Return ExtractionResult list — DB persistence is the service layer's job.

ExtractionResult is a plain dataclass (no DB imports here).
The extraction service converts these into ExtractedField + Evidence ORM objects.

Design constraints from steering file:
  - LLM NEVER fabricates values — confidence is set to 0 for absent fields.
  - Every extracted value must have source_text (citation from the document).
  - Missing required fields are returned with value=None (not omitted).
  - Conflicts (same field found with different values) are preserved as a list.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.ai.llm_client import complete_json, llm_is_available
from app.ai.prompt_builder import build_extraction_prompt
from app.core.constants import DocumentType
from app.core.exceptions import LLMError
from app.core.logging import get_logger
from app.extraction.evidence_mapper import EvidenceLocation, map_all_citations
from app.extraction.field_definitions import FieldDefinition, get_fields_for_type
from app.ingestion.models import ParsedDocument

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Result data models
# --------------------------------------------------------------------------- #

@dataclass
class ExtractedFieldResult:
    """
    A single extracted field with its evidence citation.
    Returned by the extractor; persisted by the extraction service.
    """
    field_name: str
    field_label: str
    field_value: Any                    # None = not found
    confidence: float                   # 0.0–1.0
    source_text: str                    # Raw LLM citation
    source_page: Optional[int]          # Resolved by evidence_mapper
    source_section: Optional[str]       # Resolved by evidence_mapper
    location_confidence: float          # evidence_mapper match confidence
    match_method: str                   # "exact" | "fuzzy" | "not_found"
    notes: str = ""
    extraction_timestamp: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


@dataclass
class ExtractionOutput:
    """Complete extraction result for one document."""
    document_id: str
    document_type: DocumentType
    fields: list[ExtractedFieldResult]
    missing_fields: list[str]           # field names not found
    conflicts: list[str]                # described conflicts
    extraction_notes: str
    llm_model_used: str
    total_fields_attempted: int
    fields_found: int


# --------------------------------------------------------------------------- #
# Extraction engine
# --------------------------------------------------------------------------- #

_REQUIRED_RESPONSE_KEYS = ["extracted_fields", "extraction_notes", "missing_fields"]


async def extract_fields(
    parsed_doc: ParsedDocument,
    document_type: DocumentType,
    rag_context: str = "",
) -> ExtractionOutput:
    """
    Extract structured fields from a ParsedDocument using the LLM.

    Args:
        parsed_doc:    The parsed document (from Phase 4/5).
        document_type: Classified document type (from Phase 6).
        rag_context:   Retrieved guideline text (from Phase 14 RAG, or empty).

    Returns:
        ExtractionOutput with all field results and evidence locations.

    Raises:
        LLMError: If LLM is not configured or the call fails.
    """
    if not llm_is_available():
        raise LLMError(
            "LLM is not configured. Set GROQ_API_KEY in .env to run extraction."
        )

    field_defs = get_fields_for_type(document_type)
    if not field_defs:
        logger.info(
            "No field definitions for document type — skipping extraction",
            doc_type=document_type.value,
            document_id=parsed_doc.document_id,
        )
        return ExtractionOutput(
            document_id=parsed_doc.document_id,
            document_type=document_type,
            fields=[],
            missing_fields=[],
            conflicts=[],
            extraction_notes=f"No field definitions for type {document_type.value}.",
            llm_model_used="none",
            total_fields_attempted=0,
            fields_found=0,
        )

    field_names = [f.name for f in field_defs]

    # Build prompt
    prompt = build_extraction_prompt(
        document_text=parsed_doc.full_text,
        document_type=document_type.value,
        fields_to_extract=field_names,
        rag_context=rag_context,
        document_id=parsed_doc.document_id,
    )

    logger.info(
        "Running LLM extraction",
        document_id=parsed_doc.document_id,
        doc_type=document_type.value,
        field_count=len(field_names),
    )

    # LLM call
    from app.core.config import get_settings
    settings = get_settings()

    raw_response = await complete_json(
        prompt=prompt,
        required_keys=_REQUIRED_RESPONSE_KEYS,
        temperature=settings.llm_temperature_extraction,
    )

    llm_model = _get_last_model_used()

    # Parse fields
    raw_fields: list[dict] = raw_response.get("extracted_fields", [])
    missing_fields: list[str] = raw_response.get("missing_fields", [])
    conflicts: list[str] = raw_response.get("conflicts", [])
    extraction_notes: str = str(raw_response.get("extraction_notes", ""))

    # Build a lookup of field definitions for quick access
    field_def_map: dict[str, FieldDefinition] = {f.name: f for f in field_defs}

    # Map citations to page locations
    citations: dict[str, str] = {
        item.get("field_name", ""): str(item.get("source_text", ""))
        for item in raw_fields
        if item.get("field_name") and item.get("source_text")
    }
    location_map: dict[str, EvidenceLocation] = map_all_citations(citations, parsed_doc)

    # Build ExtractionResult list
    results: list[ExtractedFieldResult] = []
    for item in raw_fields:
        fname = str(item.get("field_name", "")).strip()
        if not fname:
            continue

        fdef = field_def_map.get(fname)
        flabel = fdef.label if fdef else fname.replace("_", " ").title()

        raw_value = item.get("field_value")
        confidence = _safe_float(item.get("confidence"), default=0.5)
        source_text = str(item.get("source_text", "")).strip()
        source_page_raw = item.get("source_page")
        notes = str(item.get("notes", ""))

        # Resolve location from evidence mapper
        location = location_map.get(fname)
        resolved_page = (
            location.page_number
            if location and location.page_number
            else (_safe_int(source_page_raw) if source_page_raw else None)
        )
        resolved_section = location.section if location else None
        loc_confidence = location.confidence if location else 0.0
        match_method = location.match_method if location else "not_found"

        results.append(ExtractedFieldResult(
            field_name=fname,
            field_label=flabel,
            field_value=raw_value,
            confidence=confidence,
            source_text=source_text,
            source_page=resolved_page,
            source_section=resolved_section,
            location_confidence=loc_confidence,
            match_method=match_method,
            notes=notes,
        ))

    # Add null results for required fields not returned by LLM
    returned_names = {r.field_name for r in results}
    for fdef in field_defs:
        if fdef.required and fdef.name not in returned_names:
            results.append(ExtractedFieldResult(
                field_name=fdef.name,
                field_label=fdef.label,
                field_value=None,
                confidence=0.0,
                source_text="",
                source_page=None,
                source_section=None,
                location_confidence=0.0,
                match_method="not_found",
                notes="Required field not found by LLM.",
            ))
            if fdef.name not in missing_fields:
                missing_fields.append(fdef.name)

    fields_found = sum(1 for r in results if r.field_value is not None)

    logger.info(
        "Extraction complete",
        document_id=parsed_doc.document_id,
        doc_type=document_type.value,
        total=len(results),
        found=fields_found,
        missing=len(missing_fields),
        conflicts=len(conflicts),
        model=llm_model,
    )

    return ExtractionOutput(
        document_id=parsed_doc.document_id,
        document_type=document_type,
        fields=results,
        missing_fields=missing_fields,
        conflicts=conflicts,
        extraction_notes=extraction_notes,
        llm_model_used=llm_model,
        total_fields_attempted=len(field_defs),
        fields_found=fields_found,
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _safe_float(value: Any, default: float = 0.5) -> float:
    try:
        f = float(value)
        return max(0.0, min(f, 1.0))
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_last_model_used() -> str:
    """Best-effort: return the model name from provider settings."""
    try:
        from app.core.config import get_settings
        return get_settings().llm_model
    except Exception:
        return "unknown"
