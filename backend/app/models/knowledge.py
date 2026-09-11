"""
KnowledgeDocument and KnowledgeChunk models.

KnowledgeDocument: An approved underwriting guideline or policy document
  stored in the knowledge base. Only documents with status=ACTIVE and
  within their effective date range may be retrieved for RAG.

KnowledgeChunk: A text chunk derived from a KnowledgeDocument, with an
  embedding vector for similarity search. Each chunk retains full source
  metadata so that RAG responses can cite the exact guideline source.

IMPORTANT: Submission documents (broker-uploaded) are NEVER stored as
KnowledgeDocuments. Only admin-approved knowledge documents are indexed.

Implemented fully in Phase 11-13: Knowledge Base, Embeddings, Vector DB.
"""
from __future__ import annotations


class KnowledgeDocument:
    """Placeholder — implemented in Phase 11."""
    pass


class KnowledgeChunk:
    """Placeholder — implemented in Phase 13."""
    pass
