"""
ExtractedField and Evidence models.

ExtractedField stores a single extracted piece of information from a document.
Evidence stores the provenance for that field: which document, which page,
which section, and what exact text was used to derive the value.

Every AI-derived important fact must have an Evidence record.
The LLM is FORBIDDEN from fabricating evidence references.

Implemented fully in Phase 9: Evidence Mapping.
"""
from __future__ import annotations


class ExtractedField:
    """Placeholder — implemented in Phase 8/9."""
    pass


class Evidence:
    """Placeholder — implemented in Phase 9."""
    pass
