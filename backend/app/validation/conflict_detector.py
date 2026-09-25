"""
Conflict detector — finds the same field with materially different values
across multiple documents in a submission.

A conflict occurs when:
  - Two or more documents have extracted the same field_name, AND
  - Their effective values differ beyond an acceptable tolerance.

Tolerance rules (to avoid false positives from rounding / formatting):
  - Numbers:   relative difference > NUMERIC_TOLERANCE (default 5%)
  - Currency:  same as numbers
  - Strings:   normalised values differ (strip, lowercase, remove punctuation)
  - Dates:     differ by more than DATE_TOLERANCE_DAYS (default 7)
  - Booleans:  any disagreement is a conflict

False-positive guards:
  - We skip fields where only one document has a non-null value.
  - We skip fields with confidence < MIN_CONFIDENCE_FOR_CONFLICT on all docs
    (low-confidence extractions from OCR may have noise).
  - We skip fields in the IGNORE_FOR_CONFLICTS set (e.g. page-level notes
    that legitimately differ per document).

Each conflict produces a RuleViolation with:
  - conflicting_values: {document_id: value} for every document involved
  - affected_document_ids: list of those document IDs
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from app.core.constants import DocumentType, ValidationIssueType, ValidationSeverity
from app.core.logging import get_logger
from app.validation.rules import RuleViolation, _parse_currency, _parse_date

logger = get_logger(__name__)

NUMERIC_TOLERANCE = 0.05       # 5% relative difference
DATE_TOLERANCE_DAYS = 7        # 1 week
MIN_CONFIDENCE_FOR_CONFLICT = 0.40   # ignore very low-confidence values

# Fields that legitimately vary across document types and should not conflict
IGNORE_FOR_CONFLICTS: frozenset[str] = frozenset({
    "extraction_notes",
    "special_instructions",
    "contact_name",         # broker vs applicant contact may differ
    "notes",
    "claims_detail",        # list fields compared separately
    "class_codes",
    "additional_insureds",
    "vehicle_types",
    "lines_requested",
    "state_of_operations",
})


class DocumentFieldValue:
    """A single field-value pair from one document."""
    __slots__ = ("document_id", "document_type", "field_name", "value", "confidence")

    def __init__(
        self,
        document_id: str,
        document_type: str,
        field_name: str,
        value: Any,
        confidence: float,
    ) -> None:
        self.document_id = document_id
        self.document_type = document_type
        self.field_name = field_name
        self.value = value
        self.confidence = confidence


def detect_conflicts(
    field_values: list[DocumentFieldValue],
) -> list[RuleViolation]:
    """
    Detect field-value conflicts across documents.

    Args:
        field_values: Flat list of all extracted field values from all
                      documents in a submission.

    Returns:
        List of RuleViolation (CONFLICT type) for each conflicting field.
    """
    # Group by field_name
    by_field: dict[str, list[DocumentFieldValue]] = {}
    for fv in field_values:
        if fv.value is None:
            continue
        if fv.field_name in IGNORE_FOR_CONFLICTS:
            continue
        by_field.setdefault(fv.field_name, []).append(fv)

    violations: list[RuleViolation] = []

    for field_name, entries in by_field.items():
        # Need at least 2 entries with non-null values
        valid_entries = [e for e in entries if e.confidence >= MIN_CONFIDENCE_FOR_CONFLICT]
        if len(valid_entries) < 2:
            continue

        # Check if all values are equivalent
        conflict = _find_conflict(field_name, valid_entries)
        if conflict:
            violations.append(conflict)

    return violations


def _find_conflict(
    field_name: str,
    entries: list[DocumentFieldValue],
) -> RuleViolation | None:
    """
    Check if entries for a field conflict.
    Returns a RuleViolation if they do, None if they agree.
    """
    # Try to determine field type from first entry
    representative_value = entries[0].value
    raw_rep = _unwrap_value(representative_value)

    # Try numeric comparison first
    num_rep = _to_number(raw_rep)
    if num_rep is not None:
        return _check_numeric_conflict(field_name, entries)

    # Try date comparison
    date_rep = _parse_date(raw_rep)
    if date_rep is not None:
        return _check_date_conflict(field_name, entries)

    # String comparison
    return _check_string_conflict(field_name, entries)


def _check_numeric_conflict(
    field_name: str,
    entries: list[DocumentFieldValue],
) -> RuleViolation | None:
    nums: list[tuple[DocumentFieldValue, float]] = []
    for entry in entries:
        n = _to_number(_unwrap_value(entry.value))
        if n is not None:
            nums.append((entry, n))

    if len(nums) < 2:
        return None

    values = [n for _, n in nums]
    min_val, max_val = min(values), max(values)

    if min_val == 0 and max_val == 0:
        return None

    denom = max(abs(min_val), abs(max_val), 1e-9)
    relative_diff = abs(max_val - min_val) / denom

    if relative_diff <= NUMERIC_TOLERANCE:
        return None

    return _build_conflict(field_name, entries,
        title=f"Conflicting values for '{_label(field_name)}'",
        description=(
            f"Documents report different values for '{field_name}'. "
            f"Range: {min_val:,.2f} – {max_val:,.2f} "
            f"({relative_diff * 100:.1f}% difference)."
        ),
        suggested_action=(
            f"Review all documents and confirm the correct value for '{field_name}'. "
            "Contact the broker for clarification."
        ),
    )


def _check_date_conflict(
    field_name: str,
    entries: list[DocumentFieldValue],
) -> RuleViolation | None:
    dates: list[tuple[DocumentFieldValue, date]] = []
    for entry in entries:
        d = _parse_date(_unwrap_value(entry.value))
        if d:
            dates.append((entry, d))

    if len(dates) < 2:
        return None

    all_dates = [d for _, d in dates]
    span_days = (max(all_dates) - min(all_dates)).days

    if span_days <= DATE_TOLERANCE_DAYS:
        return None

    return _build_conflict(field_name, entries,
        title=f"Conflicting dates for '{_label(field_name)}'",
        description=(
            f"Documents show different dates for '{field_name}'. "
            f"Dates span {span_days} days: "
            f"{min(all_dates).isoformat()} – {max(all_dates).isoformat()}."
        ),
        suggested_action=(
            f"Confirm the correct {field_name.replace('_', ' ')} with the broker."
        ),
    )


def _check_string_conflict(
    field_name: str,
    entries: list[DocumentFieldValue],
) -> RuleViolation | None:
    normalised: list[tuple[DocumentFieldValue, str]] = []
    for entry in entries:
        n = _normalise_string(_unwrap_value(entry.value))
        if n:
            normalised.append((entry, n))

    if len(normalised) < 2:
        return None

    unique_values = {n for _, n in normalised}
    if len(unique_values) <= 1:
        return None

    # Additional check: very similar strings (abbrev vs full name) — skip
    if _all_similar(list(unique_values)):
        return None

    return _build_conflict(field_name, entries,
        title=f"Conflicting information for '{_label(field_name)}'",
        description=(
            f"Documents provide different values for '{field_name}': "
            f"{', '.join(repr(v) for v in list(unique_values)[:4])}."
        ),
        suggested_action=(
            f"Verify the correct value for '{field_name}' with the broker."
        ),
    )


def _build_conflict(
    field_name: str,
    entries: list[DocumentFieldValue],
    title: str,
    description: str,
    suggested_action: str,
) -> RuleViolation:
    conflicting_values = {
        e.document_id: _unwrap_value(e.value)
        for e in entries
    }
    return RuleViolation(
        issue_type=ValidationIssueType.CONFLICT,
        severity=ValidationSeverity.ERROR,
        field_name=field_name,
        title=title,
        description=description,
        suggested_action=suggested_action,
        affected_document_ids=[e.document_id for e in entries],
        conflicting_values=conflicting_values,
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _unwrap_value(value: Any) -> Any:
    """Extract the actual value from {"value": ...} wrapper or return as-is."""
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    # Try currency first
    currency = _parse_currency(value)
    if currency is not None:
        return currency
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None


def _normalise_string(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip().lower()
    s = re.sub(r"[^\w\s]", "", s)   # remove punctuation
    s = re.sub(r"\s+", " ", s)       # collapse whitespace
    return s.strip()


def _all_similar(strings: list[str]) -> bool:
    """Return True if all strings share >80% of characters (likely same value)."""
    if len(strings) < 2:
        return True
    import difflib
    for i in range(len(strings) - 1):
        ratio = difflib.SequenceMatcher(None, strings[i], strings[i + 1]).ratio()
        if ratio < 0.80:
            return False
    return True


def _label(field_name: str) -> str:
    return field_name.replace("_", " ").title()
