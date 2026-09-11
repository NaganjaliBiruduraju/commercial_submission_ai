"""
AuditLog model.

Every important state change in the system creates an AuditLog record.
This is not optional — insurance workflows require full traceability.

Tracked for every important action:
  - Who performed the action (actor_id → users.id)
  - What was changed (entity_type, entity_id)
  - What the value was before (old_value JSON)
  - What the value is after (new_value JSON)
  - When it happened (created_at)
  - Why it happened (reason — underwriter notes)
  - From where (ip_address)

AuditLog records are IMMUTABLE — they are never updated or deleted.
This ensures a forensic-quality trail for insurance compliance.

Implemented fully in Phase 2 (auth actions) and extended through Phase 18.
"""
from __future__ import annotations


class AuditLog:
    """Placeholder — implemented progressively from Phase 2."""
    pass
