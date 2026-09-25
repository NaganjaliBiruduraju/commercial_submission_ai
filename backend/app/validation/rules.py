"""
Validation rule definitions.

Rules are pure data — no DB, no HTTP, no LLM.
Each rule defines a check that can be run deterministically on extracted fields.

Three rule categories:

1. FieldRule — validates a single field value in isolation.
   Examples: annual_revenue must be positive, date must be in the future.

2. CrossFieldRule — validates a relationship between two fields
   from the same document.
   Examples: expiration_date must be after effective_date.

3. SubmissionRule — validates a property of the whole submission
   (across all documents and document types).
   Examples: ACORD 125 must be present.

All rules produce a RuleViolation if they trigger, or None if they pass.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Optional

from app.core.constants import (
    DocumentType,
    ValidationIssueType,
    ValidationSeverity,
)


# --------------------------------------------------------------------------- #
# Shared violation data model
# --------------------------------------------------------------------------- #

@dataclass
class RuleViolation:
    """A single rule violation — becomes a ValidationIssue DB record."""
    issue_type: ValidationIssueType
    severity: ValidationSeverity
    field_name: Optional[str]
    title: str
    description: str
    suggested_action: str
    affected_document_ids: list[str]          # document UUIDs as strings
    conflicting_values: dict[str, Any]        # {doc_id: value} for CONFLICTs


# --------------------------------------------------------------------------- #
# Field-level rules
# --------------------------------------------------------------------------- #

@dataclass
class FieldRule:
    """Validates a single extracted field value."""
    field_name: str
    check: Callable[[Any], str | None]  # returns error message or None
    severity: ValidationSeverity = ValidationSeverity.WARNING
    doc_types: Optional[list[DocumentType]] = None  # None = all types


def _positive_number(value: Any) -> str | None:
    """Return error if value is not a positive number."""
    try:
        n = float(str(value).replace(",", "").replace("$", "").strip())
        if n < 0:
            return f"Value {value!r} must be a non-negative number"
        return None
    except (ValueError, TypeError):
        return f"Value {value!r} is not a valid number"


def _not_future_date(value: Any) -> str | None:
    """Warn if a loss/claim date is in the future."""
    try:
        d = _parse_date(value)
        if d and d > date.today():
            return f"Date {value!r} is in the future"
        return None
    except Exception:
        return None  # non-fatal if we can't parse


def _future_date(value: Any) -> str | None:
    """Error if policy effective date is in the past by more than 90 days."""
    try:
        d = _parse_date(value)
        if d:
            delta = (date.today() - d).days
            if delta > 90:
                return f"Effective date {value!r} is more than 90 days in the past"
        return None
    except Exception:
        return None


def _valid_email(value: Any) -> str | None:
    if not value:
        return None
    pattern = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
    if not pattern.match(str(value).strip()):
        return f"Value {value!r} does not look like a valid email address"
    return None


def _experience_mod_range(value: Any) -> str | None:
    try:
        n = float(str(value).strip())
        if n < 0.5 or n > 3.0:
            return (
                f"Experience mod factor {value!r} is outside the normal range "
                f"(0.50–3.00). Verify this value."
            )
        return None
    except (ValueError, TypeError):
        return None


def _confidence_ratio(value: Any) -> str | None:
    """Coinsurance must be between 50 and 100 percent."""
    try:
        n = float(str(value).strip().rstrip("%"))
        if n < 50 or n > 100:
            return f"Coinsurance {value!r}% is outside the normal range (50–100%)"
        return None
    except (ValueError, TypeError):
        return None


FIELD_RULES: list[FieldRule] = [
    # Financial fields — must be non-negative
    FieldRule("annual_revenue", _positive_number, ValidationSeverity.ERROR,
              doc_types=[DocumentType.ACORD_APPLICATION, DocumentType.ACORD_GL]),
    FieldRule("total_payroll", _positive_number, ValidationSeverity.ERROR,
              doc_types=[DocumentType.ACORD_WORKERS_COMP]),
    FieldRule("building_value", _positive_number, ValidationSeverity.ERROR,
              doc_types=[DocumentType.ACORD_PROPERTY]),
    FieldRule("total_paid", _positive_number, ValidationSeverity.WARNING,
              doc_types=[DocumentType.LOSS_RUN]),
    FieldRule("total_incurred", _positive_number, ValidationSeverity.WARNING,
              doc_types=[DocumentType.LOSS_RUN]),
    FieldRule("total_revenue", _positive_number, ValidationSeverity.WARNING,
              doc_types=[DocumentType.FINANCIAL_STATEMENT]),

    # Date fields
    FieldRule("policy_effective_date", _future_date, ValidationSeverity.WARNING),

    # Format checks
    FieldRule("broker_email", _valid_email, ValidationSeverity.WARNING),
    FieldRule("contact_email", _valid_email, ValidationSeverity.WARNING),

    # Range checks
    FieldRule("experience_mod", _experience_mod_range, ValidationSeverity.WARNING,
              doc_types=[DocumentType.ACORD_WORKERS_COMP]),
    FieldRule("coinsurance_pct", _confidence_ratio, ValidationSeverity.WARNING,
              doc_types=[DocumentType.ACORD_PROPERTY]),
]


# --------------------------------------------------------------------------- #
# Cross-field rules
# --------------------------------------------------------------------------- #

@dataclass
class CrossFieldRule:
    """Validates a relationship between two fields in the same document."""
    field_a: str
    field_b: str
    check: Callable[[Any, Any], str | None]  # returns error or None
    severity: ValidationSeverity = ValidationSeverity.WARNING
    doc_types: Optional[list[DocumentType]] = None


def _expiry_after_effective(effective: Any, expiry: Any) -> str | None:
    try:
        d_eff = _parse_date(effective)
        d_exp = _parse_date(expiry)
        if d_eff and d_exp and d_exp <= d_eff:
            return (
                f"Expiration date ({expiry}) must be after "
                f"effective date ({effective})"
            )
        return None
    except Exception:
        return None


def _revenue_vs_employees(revenue: Any, employees: Any) -> str | None:
    """Warn if revenue/employee ratio is unusually low or high."""
    try:
        rev = _parse_currency(revenue)
        emp = float(str(employees).strip())
        if emp <= 0 or rev is None:
            return None
        ratio = rev / emp
        # Revenue per employee below $5k or above $50M is unusual
        if ratio < 5_000:
            return (
                f"Revenue per employee (${ratio:,.0f}) is unusually low. "
                "Verify annual revenue and employee count."
            )
        if ratio > 50_000_000:
            return (
                f"Revenue per employee (${ratio:,.0f}) is unusually high. "
                "Verify annual revenue and employee count."
            )
        return None
    except (ValueError, TypeError):
        return None


CROSS_FIELD_RULES: list[CrossFieldRule] = [
    CrossFieldRule(
        "policy_effective_date", "policy_expiration_date",
        _expiry_after_effective,
        ValidationSeverity.ERROR,
    ),
    CrossFieldRule(
        "annual_revenue", "employee_count",
        _revenue_vs_employees,
        ValidationSeverity.WARNING,
        doc_types=[DocumentType.ACORD_APPLICATION],
    ),
]


# --------------------------------------------------------------------------- #
# Submission-level rules (cross-document)
# --------------------------------------------------------------------------- #

@dataclass
class SubmissionRule:
    """Validates a property of the whole submission."""
    rule_id: str
    description: str
    check: Callable[[set[DocumentType]], RuleViolation | None]


def _acord_125_required(present_types: set[DocumentType]) -> RuleViolation | None:
    if DocumentType.ACORD_APPLICATION not in present_types:
        return RuleViolation(
            issue_type=ValidationIssueType.MISSING,
            severity=ValidationSeverity.WARNING,
            field_name=None,
            title="ACORD 125 Application Not Found",
            description=(
                "No ACORD 125 Commercial Lines Application was identified in this submission. "
                "ACORD 125 is the primary application form required for commercial underwriting."
            ),
            suggested_action=(
                "Request the ACORD 125 form from the broker before proceeding."
            ),
            affected_document_ids=[],
            conflicting_values={},
        )
    return None


def _loss_run_required(present_types: set[DocumentType]) -> RuleViolation | None:
    coverage_types = {
        DocumentType.ACORD_APPLICATION, DocumentType.ACORD_GL,
        DocumentType.ACORD_PROPERTY, DocumentType.ACORD_WORKERS_COMP,
    }
    if coverage_types & present_types and DocumentType.LOSS_RUN not in present_types:
        return RuleViolation(
            issue_type=ValidationIssueType.MISSING,
            severity=ValidationSeverity.WARNING,
            field_name=None,
            title="Loss Run Report Not Provided",
            description=(
                "A loss run report was not found in this submission. "
                "Loss runs are required to evaluate prior claims history."
            ),
            suggested_action=(
                "Request 3-5 years of loss run reports from the broker."
            ),
            affected_document_ids=[],
            conflicting_values={},
        )
    return None


SUBMISSION_RULES: list[SubmissionRule] = [
    SubmissionRule("acord_125_required", "ACORD 125 must be present", _acord_125_required),
    SubmissionRule("loss_run_recommended", "Loss run report recommended", _loss_run_required),
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_DATE_FORMATS = [
    "%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d",
    "%m/%d/%y", "%d/%m/%Y", "%B %d, %Y",
]


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    s = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_currency(value: Any) -> float | None:
    if not value:
        return None
    try:
        cleaned = re.sub(r"[$,\s]", "", str(value))
        # Handle 'M' / 'K' suffixes
        if cleaned.upper().endswith("M"):
            return float(cleaned[:-1]) * 1_000_000
        if cleaned.upper().endswith("K"):
            return float(cleaned[:-1]) * 1_000
        return float(cleaned)
    except (ValueError, TypeError):
        return None
