"""
Validation orchestrator — runs all deterministic checks and returns a
unified list of ValidationIssue-ready results.

Pipeline (all deterministic Python — no LLM):
  1. Field-level rules  (FieldRule checks)     → INVALID issues
  2. Cross-field rules  (CrossFieldRule checks) → INVALID issues
  3. Conflict detection (same field, different values across docs) → CONFLICT
  4. Missing field detection                   → MISSING issues
  5. Missing coverage form detection           → MISSING issues
  6. Submission-level rules (ACORD 125 present, loss run present) → MISSING/WARNING

The validator is pure — it receives data, returns violations.
No DB access, no HTTP, no LLM.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.constants import DocumentType, ValidationIssueType, ValidationSeverity
from app.core.logging import get_logger
from app.validation.conflict_detector import (
    DocumentFieldValue,
    detect_conflicts,
)
from app.validation.missing_detector import (
    detect_incomplete_coverage,
    detect_missing_fields,
)
from app.validation.rules import (
    CROSS_FIELD_RULES,
    FIELD_RULES,
    SUBMISSION_RULES,
    RuleViolation,
)

logger = get_logger(__name__)


def _unwrap(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


@dataclass
class FieldInput:
    """Input data for one extracted field from one document."""
    document_id: str
    document_type: DocumentType
    field_name: str
    value: Any           # raw stored value (may be {"value": ...} wrapped)
    confidence: float


@dataclass
class ValidationReport:
    """Complete validation results for a submission."""
    violations: list[RuleViolation]
    total_issues: int
    error_count: int
    warning_count: int
    conflict_count: int
    missing_count: int
    invalid_count: int


def run_validation(
    fields: list[FieldInput],
    present_doc_types: set[DocumentType],
) -> ValidationReport:
    """
    Run all deterministic validation checks.

    Args:
        fields:            All extracted fields from all documents.
        present_doc_types: Set of document types present in the submission.

    Returns:
        ValidationReport with all violations found.
    """
    violations: list[RuleViolation] = []

    # ------------------------------------------------------------------ #
    # 1. Field-level rules
    # ------------------------------------------------------------------ #
    for rule in FIELD_RULES:
        for fi in fields:
            # Skip if rule is type-restricted and this doc isn't in the list
            if rule.doc_types and fi.document_type not in rule.doc_types:
                continue
            if fi.field_name != rule.field_name:
                continue
            raw = _unwrap(fi.value)
            if raw is None:
                continue

            error_msg = rule.check(raw)
            if error_msg:
                violations.append(RuleViolation(
                    issue_type=ValidationIssueType.INVALID,
                    severity=rule.severity,
                    field_name=fi.field_name,
                    title=f"Invalid Value: {fi.field_name.replace('_', ' ').title()}",
                    description=error_msg,
                    suggested_action=(
                        f"Verify the value for '{fi.field_name}' in the source document."
                    ),
                    affected_document_ids=[fi.document_id],
                    conflicting_values={fi.document_id: raw},
                ))

    # ------------------------------------------------------------------ #
    # 2. Cross-field rules (within same document)
    # ------------------------------------------------------------------ #
    # Group fields by document for cross-field checks
    by_doc: dict[str, dict[str, Any]] = {}
    by_doc_type: dict[str, DocumentType] = {}
    for fi in fields:
        by_doc.setdefault(fi.document_id, {})[fi.field_name] = _unwrap(fi.value)
        by_doc_type[fi.document_id] = fi.document_type

    for rule in CROSS_FIELD_RULES:
        for doc_id, doc_fields in by_doc.items():
            doc_type = by_doc_type[doc_id]
            if rule.doc_types and doc_type not in rule.doc_types:
                continue
            val_a = doc_fields.get(rule.field_a)
            val_b = doc_fields.get(rule.field_b)
            if val_a is None or val_b is None:
                continue

            error_msg = rule.check(val_a, val_b)
            if error_msg:
                violations.append(RuleViolation(
                    issue_type=ValidationIssueType.INVALID,
                    severity=rule.severity,
                    field_name=f"{rule.field_a}/{rule.field_b}",
                    title=(
                        f"Cross-Field Issue: "
                        f"{rule.field_a.replace('_', ' ').title()} vs "
                        f"{rule.field_b.replace('_', ' ').title()}"
                    ),
                    description=error_msg,
                    suggested_action=(
                        "Verify both field values and correct any discrepancies."
                    ),
                    affected_document_ids=[doc_id],
                    conflicting_values={
                        rule.field_a: val_a,
                        rule.field_b: val_b,
                    },
                ))

    # ------------------------------------------------------------------ #
    # 3. Conflict detection (same field, different values across docs)
    # ------------------------------------------------------------------ #
    doc_field_values = [
        DocumentFieldValue(
            document_id=fi.document_id,
            document_type=fi.document_type.value,
            field_name=fi.field_name,
            value=fi.value,
            confidence=fi.confidence,
        )
        for fi in fields
        if fi.value is not None
    ]
    violations.extend(detect_conflicts(doc_field_values))

    # ------------------------------------------------------------------ #
    # 4. Missing field detection
    # ------------------------------------------------------------------ #
    violations.extend(
        detect_missing_fields(
            extracted_by_doc={
                doc_id: fields_dict
                for doc_id, fields_dict in by_doc.items()
            },
            doc_type_by_doc=by_doc_type,
        )
    )

    # ------------------------------------------------------------------ #
    # 5. Missing coverage forms
    # ------------------------------------------------------------------ #
    # Extract lines_requested from any ACORD_APPLICATION document
    lines_requested: list[str] = []
    for fi in fields:
        if (
            fi.document_type == DocumentType.ACORD_APPLICATION
            and fi.field_name == "lines_requested"
            and fi.value is not None
        ):
            raw = _unwrap(fi.value)
            if isinstance(raw, list):
                lines_requested = [str(x) for x in raw]
            elif raw:
                lines_requested = [str(raw)]
            break

    violations.extend(
        detect_incomplete_coverage(present_doc_types, lines_requested)
    )

    # ------------------------------------------------------------------ #
    # 6. Submission-level rules
    # ------------------------------------------------------------------ #
    for rule in SUBMISSION_RULES:
        violation = rule.check(present_doc_types)
        if violation:
            violations.append(violation)

    # ------------------------------------------------------------------ #
    # Build report
    # ------------------------------------------------------------------ #
    error_count = sum(1 for v in violations if v.severity == ValidationSeverity.ERROR)
    warning_count = sum(1 for v in violations if v.severity == ValidationSeverity.WARNING)
    conflict_count = sum(1 for v in violations if v.issue_type == ValidationIssueType.CONFLICT)
    missing_count = sum(1 for v in violations if v.issue_type == ValidationIssueType.MISSING)
    invalid_count = sum(1 for v in violations if v.issue_type == ValidationIssueType.INVALID)

    logger.info(
        "Validation complete",
        total=len(violations),
        errors=error_count,
        warnings=warning_count,
        conflicts=conflict_count,
        missing=missing_count,
        invalid=invalid_count,
    )

    return ValidationReport(
        violations=violations,
        total_issues=len(violations),
        error_count=error_count,
        warning_count=warning_count,
        conflict_count=conflict_count,
        missing_count=missing_count,
        invalid_count=invalid_count,
    )
