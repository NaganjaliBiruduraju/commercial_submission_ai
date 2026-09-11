"""
Document classifier — orchestrator.

Pipeline:
  1. Run rules_classifier.classify_with_rules() — fast, deterministic, free.
  2. If confidence >= HIGH_CONFIDENCE_THRESHOLD → accept rules result.
  3. If result is ambiguous OR confidence is low → call LLM fallback.
  4. Merge: take the higher-confidence result from rules vs LLM.
  5. Return a ClassificationResult.

This module is the only entry point callers should use.
It is async because the LLM path is async (Groq HTTP call).

Confidence thresholds:
  HIGH_CONFIDENCE_THRESHOLD = 0.75  → rules result accepted without LLM
  LOW_CONFIDENCE_THRESHOLD  = 0.30  → set by rules_classifier (returns OTHER)
  AMBIGUITY_GAP             = 0.12  → set by rules_classifier (is_ambiguous flag)

The LLM is ONLY invoked when the rules result is uncertain.
Estimated LLM invocation rate: ~15–25% of documents in typical submissions
(most ACORD forms are unambiguous with the rule patterns above).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.constants import DocumentType
from app.core.logging import get_logger
from app.classification.rules_classifier import (
    RulesClassificationResult,
    classify_with_rules,
)
from app.classification.llm_classifier import LLMClassificationResult, classify_with_llm

logger = get_logger(__name__)

HIGH_CONFIDENCE_THRESHOLD = 0.75  # rules result accepted without LLM


@dataclass
class ClassificationResult:
    """Final classification result returned to the DB service."""
    document_type: DocumentType
    confidence: float           # 0.0–1.0
    classification_reason: str
    classified_by: str          # "deterministic" | "llm:<model>" | "deterministic+llm"
    alternative_type: Optional[DocumentType] = None


async def classify_document(
    text: str,
    extension: str = "",
    filename: str = "",
    use_llm: bool = True,
) -> ClassificationResult:
    """
    Classify a document using rules + optional LLM fallback.

    Args:
        text:       Document full text (ParsedDocument.full_text).
        extension:  Lowercase file extension.
        filename:   Original filename (for extension hint + logging).
        use_llm:    Set False to skip LLM even for ambiguous results
                    (useful in tests or when Groq key not configured).

    Returns:
        ClassificationResult with the best document type.
    """
    if not text or not text.strip():
        return ClassificationResult(
            document_type=DocumentType.OTHER,
            confidence=0.0,
            classification_reason="Document has no extractable text — cannot classify.",
            classified_by="deterministic",
        )

    # ------------------------------------------------------------------ #
    # Step 1: Deterministic rules
    # ------------------------------------------------------------------ #
    rules_result: RulesClassificationResult = classify_with_rules(
        text=text,
        extension=extension,
        filename=filename,
    )

    logger.debug(
        "Rules classification",
        doc_type=rules_result.document_type.value,
        confidence=rules_result.confidence,
        is_ambiguous=rules_result.is_ambiguous,
        filename=filename,
    )

    # Fast path: high-confidence, unambiguous rules result
    if (
        not rules_result.is_ambiguous
        and rules_result.confidence >= HIGH_CONFIDENCE_THRESHOLD
    ):
        return ClassificationResult(
            document_type=rules_result.document_type,
            confidence=rules_result.confidence,
            classification_reason=rules_result.reason,
            classified_by="deterministic",
            alternative_type=rules_result.alternative_type,
        )

    # ------------------------------------------------------------------ #
    # Step 2: LLM fallback for ambiguous / low-confidence results
    # ------------------------------------------------------------------ #
    if not use_llm:
        # No LLM — return rules result as-is
        return ClassificationResult(
            document_type=rules_result.document_type,
            confidence=rules_result.confidence,
            classification_reason=rules_result.reason + " [LLM disabled]",
            classified_by="deterministic",
            alternative_type=rules_result.alternative_type,
        )

    # Pass candidate types to the LLM to narrow the token budget
    candidates = None
    if rules_result.is_ambiguous and rules_result.alternative_type:
        candidates = [rules_result.document_type, rules_result.alternative_type]

    try:
        llm_result: LLMClassificationResult = await classify_with_llm(
            text=text,
            candidate_types=candidates,
            filename=filename,
        )
    except Exception as exc:
        # LLM failure is non-fatal — fall back to rules result with a warning
        logger.warning(
            "LLM classification failed — using rules result",
            error=str(exc),
            filename=filename,
        )
        return ClassificationResult(
            document_type=rules_result.document_type,
            confidence=rules_result.confidence,
            classification_reason=(
                rules_result.reason
                + f" [LLM fallback failed: {type(exc).__name__}]"
            ),
            classified_by="deterministic",
            alternative_type=rules_result.alternative_type,
        )

    logger.debug(
        "LLM classification",
        doc_type=llm_result.document_type.value,
        confidence=llm_result.confidence,
        model=llm_result.model_used,
        filename=filename,
    )

    # ------------------------------------------------------------------ #
    # Step 3: Merge — pick the higher-confidence result
    # ------------------------------------------------------------------ #
    if llm_result.confidence >= rules_result.confidence:
        merged_type = llm_result.document_type
        merged_confidence = llm_result.confidence
        merged_reason = llm_result.reason
        classified_by = f"llm:{llm_result.model_used}"
        alt = llm_result.alternative_type or rules_result.alternative_type
    else:
        merged_type = rules_result.document_type
        merged_confidence = rules_result.confidence
        merged_reason = rules_result.reason
        classified_by = "deterministic+llm"
        alt = rules_result.alternative_type or llm_result.alternative_type

    # Agreement bonus: if both agree, boost confidence slightly
    if rules_result.document_type == llm_result.document_type:
        merged_confidence = min(merged_confidence + 0.05, 1.0)
        merged_reason += " [rules and LLM agree]"
        classified_by = "deterministic+llm"

    logger.info(
        "Classification complete",
        doc_type=merged_type.value,
        confidence=round(merged_confidence, 3),
        classified_by=classified_by,
        filename=filename,
    )

    return ClassificationResult(
        document_type=merged_type,
        confidence=round(merged_confidence, 3),
        classification_reason=merged_reason[:1000],
        classified_by=classified_by,
        alternative_type=alt,
    )
