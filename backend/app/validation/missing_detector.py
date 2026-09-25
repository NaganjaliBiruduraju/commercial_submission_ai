"""
Missing field detector — identifies required fields absent from a submission.

Three types of missing-field issues:

1. REQUIRED FIELD MISSING — A field marked required=True in field_definitions
   was not extracted from any document of the relevant type.
   Severity: ERROR for primary fields, WARNING for secondary.

2. INCOMPLETE SUBMISSION — A coverage type was requested but the corresponding
   ACORD form is missing from the submission entirely.
   e.g. GL coverage requested but no ACORD 126 found.

3. FIELD PRESENT BUT EMPTY — A field was extracted but with a null value and
   zero confidence (the LLM found the label but not the value).
   Severity: WARNING.
"""
from __future__ import annotations

from typing import Any

from app.core.constants import DocumentType, ValidationIssueType, ValidationSeverity
from app.core.logging import get_logger
from app.extraction.field_definitions import get_required_fields
from app.validation.rules import RuleViolation

logger = get_logger(__name__)

# Fields always required regardless of document type
GLOBALLY_REQUIRED: list[str] = [
    "applicant_name",
    "policy_effective_date",
]

# If these document types are present, the corresponding ACORD form is expected
_COVERAGE_TO_ACORD: dict[str, DocumentType] = {
    "general liability": DocumentType.ACORD_GL,
    "gl": DocumentType.ACORD_GL,
    "property": DocumentType.ACORD_PROPERTY,
    "auto": DocumentType.ACORD_AUTO,
    "business auto": DocumentType.ACORD_AUTO,
    "workers comp": DocumentType.ACORD_WORKERS_COMP,
    "workers compensation": DocumentType.ACORD_WORKERS_COMP,
    "umbrella": DocumentType.ACORD_UMBRELLA,
    "excess": DocumentType.ACORD_UMBRELLA,
}


def detect_missing_fields(
    extracted_by_doc: dict[str, dict[str, Any]],
    doc_type_by_doc: dict[str, DocumentType],
) -> list[RuleViolation]:
    """
    Detect missing required fields.

    Args:
        extracted_by_doc:  {document_id: {field_name: value_or_None}}
        doc_type_by_doc:   {document_id: DocumentType}

    Returns:
        List of RuleViolation (MISSING type).
    """
    violations: list[RuleViolation] = []

    # Build a flat view: field_name → list of (doc_id, value, confidence) across all docs
    all_fields: dict[str, list[tuple[str, Any]]] = {}
    for doc_id, fields in extracted_by_doc.items():
        for fname, fvalue in fields.items():
            all_fields.setdefault(fname, []).append((doc_id, fvalue))

    # 1. Globally required fields
    for field_name in GLOBALLY_REQUIRED:
        entries = all_fields.get(field_name, [])
        found = any(v is not None for _, v in entries)
        if not found:
            violations.append(RuleViolation(
                issue_type=ValidationIssueType.MISSING,
                severity=ValidationSeverity.ERROR,
                field_name=field_name,
                title=f"Required Field Missing: {_label(field_name)}",
                description=(
                    f"'{_label(field_name)}' was not found in any document in this submission. "
                    "This field is required for underwriting."
                ),
                suggested_action=f"Request the {_label(field_name)} from the broker.",
                affected_document_ids=[],
                conflicting_values={},
            ))

    # 2. Per-document-type required fields
    for doc_id, doc_type in doc_type_by_doc.items():
        required = get_required_fields(doc_type)
        doc_fields = extracted_by_doc.get(doc_id, {})

        for field_def in required:
            fname = field_def.name
            value = doc_fields.get(fname)

            # Skip globally required (already checked above)
            if fname in GLOBALLY_REQUIRED:
                continue

            if value is None:
                violations.append(RuleViolation(
                    issue_type=ValidationIssueType.MISSING,
                    severity=ValidationSeverity.WARNING,
                    field_name=fname,
                    title=f"Required Field Missing: {field_def.label}",
                    description=(
                        f"'{field_def.label}' was not found in document "
                        f"(type: {doc_type.value}). "
                        f"{field_def.description or ''}"
                    ).strip(),
                    suggested_action=(
                        f"Request the '{field_def.label}' from the broker or "
                        "locate it in the submitted documents."
                    ),
                    affected_document_ids=[doc_id],
                    conflicting_values={},
                ))

    return _deduplicate(violations)


def detect_incomplete_coverage(
    present_doc_types: set[DocumentType],
    lines_requested: list[str] | None,
) -> list[RuleViolation]:
    """
    Check if coverage types mentioned in lines_requested have corresponding forms.

    Args:
        present_doc_types: Set of document types found in the submission.
        lines_requested:   List of coverage lines from the ACORD 125.

    Returns:
        List of RuleViolation for missing coverage forms.
    """
    if not lines_requested:
        return []

    violations: list[RuleViolation] = []

    for line in lines_requested:
        line_lower = str(line).lower().strip()
        expected_type = _COVERAGE_TO_ACORD.get(line_lower)

        if expected_type and expected_type not in present_doc_types:
            violations.append(RuleViolation(
                issue_type=ValidationIssueType.MISSING,
                severity=ValidationSeverity.WARNING,
                field_name=None,
                title=f"Missing Form for Requested Coverage: {line}",
                description=(
                    f"Coverage '{line}' was requested but the corresponding form "
                    f"({expected_type.value}) was not found in the submission."
                ),
                suggested_action=(
                    f"Request the {expected_type.value.replace('_', ' ').title()} "
                    "form from the broker."
                ),
                affected_document_ids=[],
                conflicting_values={},
            ))

    return violations


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _deduplicate(violations: list[RuleViolation]) -> list[RuleViolation]:
    """Remove duplicate violations for the same field_name."""
    seen: set[tuple] = set()
    unique: list[RuleViolation] = []
    for v in violations:
        key = (v.issue_type, v.field_name, v.title)
        if key not in seen:
            seen.add(key)
            unique.append(v)
    return unique


def _label(field_name: str) -> str:
    return field_name.replace("_", " ").title()
