"""
ValidationIssue model.

Stores the output of the deterministic validation engine.
Validation issues include:
  - CONFLICT:  Two documents report different values for the same field
  - MISSING:   A required field is absent from all documents
  - INVALID:   A field contains an invalid value (e.g., negative employee count)
  - WARNING:   A non-blocking concern for the underwriter

The LLM does NOT generate ValidationIssues.
Python business rules calculate them.
The LLM may later generate human-readable explanations of existing issues.

Implemented fully in Phase 10: Deterministic Validation.
"""
from __future__ import annotations


class ValidationIssue:
    """Placeholder — implemented in Phase 10."""
    pass
