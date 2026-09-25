"""
Prompt-driven extraction engine.

The output structure is defined entirely by the prompt — not by hardcoded
field lists or JSON schemas in the code.

How it works:
  1. The caller builds a prompt (or passes one directly) that describes
     exactly what to extract and in what format.
  2. complete_freeform() sends that prompt to the LLM as-is.
  3. The raw response is returned — whatever shape the prompt asked for.

This means:
  - You can ask for a markdown table → you get a markdown table.
  - You can ask for JSON with your own keys → you get that JSON.
  - You can ask for a plain paragraph summary → you get that.
  - You can mix structured and unstructured sections in one response.

The field_definitions module is still used as a REFERENCE to build
default prompts (so you don't have to write one from scratch), but
those prompts are just suggestions — you can override them entirely.

ExtractionOutput wraps the response so the DB service can persist it
and the API can return it consistently.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.ai.llm_client import complete_freeform, llm_is_available
from app.core.constants import DocumentType
from app.core.exceptions import LLMError
from app.core.logging import get_logger
from app.ingestion.models import ParsedDocument

logger = get_logger(__name__)

# Default system instruction injected when no custom system prompt is given.
# Kept minimal so the user prompt has full control.
_DEFAULT_SYSTEM = (
    "You are an AI assistant analyzing commercial insurance documents. "
    "Extract and analyze information exactly as requested in the prompt. "
    "Only use information present in the document. "
    "Never fabricate values. "
    "Do not add commentary unless the prompt asks for it."
)


@dataclass
class ExtractionOutput:
    """
    Wraps the LLM response for one document.

    raw_response:    Exactly what the LLM returned — shaped by the prompt.
    parsed_data:     If the response was valid JSON, this holds the parsed dict.
                     None if the response was free-text / markdown / other format.
    prompt_used:     The exact prompt that produced this output (for audit).
    document_id:     Source document UUID string.
    document_type:   Classified document type.
    llm_model_used:  Model that produced the response.
    extraction_timestamp: When extraction ran.
    """
    document_id: str
    document_type: DocumentType
    raw_response: str
    prompt_used: str
    llm_model_used: str
    parsed_data: Any = None          # dict/list if JSON, None otherwise
    extraction_timestamp: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    warnings: list[str] = field(default_factory=list)


def _try_parse_json(text: str) -> Any:
    """
    Try to parse the response as JSON. Returns parsed object or None.
    Strips common LLM formatting artifacts (```json fences).
    """
    stripped = text.strip()
    for fence in ("```json", "```"):
        if stripped.startswith(fence):
            stripped = stripped[len(fence):]
    if stripped.endswith("```"):
        stripped = stripped[:-3]
    stripped = stripped.strip()
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None


async def extract_with_prompt(
    parsed_doc: ParsedDocument,
    prompt: str,
    document_type: DocumentType | None = None,
    system_prompt: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> ExtractionOutput:
    """
    Extract information from a document using your own prompt.

    The output is shaped entirely by what your prompt asks for.

    Args:
        parsed_doc:    Parsed document from Phase 4/5 (provides the text).
        prompt:        Your extraction prompt. Use {document_text} as a
                       placeholder and it will be replaced with the doc text.
                       Or include the text inline — your choice.
        document_type: Document type for logging (optional).
        system_prompt: Override the default system prompt entirely.
        temperature:   LLM temperature (default 0.1 for extraction).
        max_tokens:    Max response tokens.

    Returns:
        ExtractionOutput with raw_response and (if JSON) parsed_data.
    """
    if not llm_is_available():
        raise LLMError(
            "LLM not configured. Set GROQ_API_KEY in .env."
        )

    doc_type = document_type or DocumentType.OTHER

    # Inject document text into prompt if placeholder is present
    if "{document_text}" in prompt:
        final_prompt = prompt.replace("{document_text}", parsed_doc.full_text)
    else:
        # Append document text after the prompt
        final_prompt = (
            f"{prompt}\n\n"
            f"DOCUMENT TEXT:\n"
            f"<document_text>\n{parsed_doc.full_text}\n</document_text>"
        )

    from app.core.config import get_settings
    settings = get_settings()

    logger.info(
        "Running prompt-driven extraction",
        document_id=parsed_doc.document_id,
        doc_type=doc_type.value,
        prompt_chars=len(final_prompt),
    )

    raw = await complete_freeform(
        prompt=final_prompt,
        system_prompt=system_prompt or _DEFAULT_SYSTEM,
        temperature=temperature if temperature is not None else settings.llm_temperature_extraction,
        max_tokens=max_tokens or settings.llm_max_tokens,
        document_id=parsed_doc.document_id,
        apply_pii_scrub=True,
        add_disclaimer=False,
    )

    parsed = _try_parse_json(raw)

    warnings: list[str] = []
    if not raw.strip():
        warnings.append("LLM returned an empty response.")

    logger.info(
        "Extraction complete",
        document_id=parsed_doc.document_id,
        doc_type=doc_type.value,
        response_chars=len(raw),
        is_json=parsed is not None,
        model=settings.llm_model,
    )

    return ExtractionOutput(
        document_id=parsed_doc.document_id,
        document_type=doc_type,
        raw_response=raw,
        prompt_used=final_prompt[:2000],   # store first 2000 chars for audit
        llm_model_used=settings.llm_model,
        parsed_data=parsed,
        warnings=warnings,
    )


async def extract_with_default_prompt(
    parsed_doc: ParsedDocument,
    document_type: DocumentType,
    rag_context: str = "",
    temperature: float | None = None,
) -> ExtractionOutput:
    """
    Extract using the default prompt for this document type.

    Builds the prompt from the field definitions and template files,
    but the LLM is free to organize its response however best fits
    the document — the prompt does not enforce a rigid JSON schema.

    Use extract_with_prompt() to supply your own prompt instead.
    """
    from app.extraction.field_definitions import get_fields_for_type

    field_defs = get_fields_for_type(document_type)
    field_descriptions = "\n".join(
        f"- {f.label} ({f.name})"
        + (f": {f.description}" if f.description else "")
        + (" [REQUIRED]" if f.required else "")
        for f in field_defs
    ) if field_defs else "Extract all relevant insurance information."

    rag_section = (
        f"\nUNDERWRITING GUIDELINES (from knowledge base):\n{rag_context}\n"
        if rag_context else ""
    )

    prompt = f"""Analyze the following {document_type.value.replace('_', ' ').title()} document and extract the information listed below.
{rag_section}
FIELDS TO EXTRACT:
{field_descriptions}

For each piece of information you find:
- State the field name and its value
- Quote the exact text from the document that supports this value
- Rate your confidence (high / medium / low)
- If a required field is not present, say so clearly

Organize your response in whatever format best presents this information clearly.
You may use JSON, a structured list, a table, or prose — whichever fits the document.

{{document_text}}"""

    return await extract_with_prompt(
        parsed_doc=parsed_doc,
        prompt=prompt,
        document_type=document_type,
        temperature=temperature,
    )
