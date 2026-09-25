"""
Validation layer — deterministic Python checks on extracted fields.

No LLM is used here. All issues are produced by rule engines.

Public API:
  run_validation(fields, present_doc_types) → ValidationReport
  detect_conflicts(field_values)            → list[RuleViolation]
  detect_missing_fields(...)               → list[RuleViolation]
"""
from app.validation.validator import FieldInput, ValidationReport, run_validation
from app.validation.rules import RuleViolation, FIELD_RULES, CROSS_FIELD_RULES, SUBMISSION_RULES
from app.validation.conflict_detector import DocumentFieldValue, detect_conflicts
from app.validation.missing_detector import detect_missing_fields, detect_incomplete_coverage

__all__ = [
    "FieldInput",
    "ValidationReport",
    "run_validation",
    "RuleViolation",
    "FIELD_RULES",
    "CROSS_FIELD_RULES",
    "SUBMISSION_RULES",
    "DocumentFieldValue",
    "detect_conflicts",
    "detect_missing_fields",
    "detect_incomplete_coverage",
]
