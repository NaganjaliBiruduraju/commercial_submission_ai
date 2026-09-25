"""
Vector store — similarity search over KnowledgeChunk embeddings.

Phase 13 plan: migrate to native pgvector (<=> cosine operator).
Phase 12 (now): in-memory cosine similarity search using numpy.

The in-memory approach:
  - Loads all active+indexed chunk embeddings into a numpy matrix on first query.
  - Computes cosine similarity as a matrix dot product (embeddings are L2-normalized).
  - Returns top-k chunks sorted by similarity.
  - Cache is invalidated when new chunks are indexed (via invalidate_cache()).

Performance:
  A typical knowledge base has 500–5000 chunks × 384 dims ≈ 1.5–15 MB in RAM.
  For this size, numpy is faster than a round-trip to PostgreSQL for each query.
  At 50 000+ chunks, switch to pgvector.

Thread safety: the cache is replaced atomically (Python GIL covers this for
simple assignments). For production scale use asyncio.Lock.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Cache: (embeddings_matrix, chunk_ids, chunk_texts, chunk_metadata)
_cache: dict | None = None
_cache_lock = asyncio.Lock()


@dataclass
class SimilarChunk:
    """A retrieved knowledge chunk with its similarity score."""
    chunk_id: str
    document_id: str
    chunk_text: str
    chunk_index: int
    page_number: int | None
    section: str | None
    similarity: float        # 0.0–1.0 cosine similarity
    metadata: dict           # title, category, version


async def build_index(db: Any) -> int:
    """
    Build (or rebuild) the in-memory vector index from DB.

    Loads all chunks from ACTIVE indexed KnowledgeDocuments.
    Returns number of chunks indexed.
    """
    global _cache

    from app.repositories.knowledge_repository import KnowledgeChunkRepository

    repo = KnowledgeChunkRepository(db)
    chunks = await repo.get_all_indexed_chunks()

    if not chunks:
        async with _cache_lock:
            _cache = None
        logger.info("Vector index empty — no active indexed chunks")
        return 0

    try:
        import numpy as np
    except ImportError:
        raise ImportError("numpy is required for vector search. pip install numpy")

    embeddings = []
    chunk_ids = []
    chunk_texts = []
    chunk_meta = []

    for chunk in chunks:
        if not chunk.embedding:
            continue
        emb = chunk.embedding
        if isinstance(emb, list):
            embeddings.append(emb)
            chunk_ids.append(str(chunk.id))
            chunk_texts.append(chunk.chunk_text)
            chunk_meta.append({
                "document_id": str(chunk.document_id),
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "section": chunk.section,
                "metadata": chunk.chunk_metadata or {},
            })

    if not embeddings:
        async with _cache_lock:
            _cache = None
        return 0

    matrix = np.array(embeddings, dtype=np.float32)

    async with _cache_lock:
        _cache = {
            "matrix": matrix,
            "chunk_ids": chunk_ids,
            "chunk_texts": chunk_texts,
            "chunk_meta": chunk_meta,
        }

    logger.info("Vector index built", chunk_count=len(chunk_ids))
    return len(chunk_ids)


async def search(
    query_embedding: list[float],
    top_k: int = 5,
    min_similarity: float = 0.30,
) -> list[SimilarChunk]:
    """
    Find the top-k most similar chunks to a query embedding.

    Args:
        query_embedding: L2-normalized query vector (384 dims).
        top_k:           Maximum number of results to return.
        min_similarity:  Minimum cosine similarity threshold.

    Returns:
        List of SimilarChunk sorted by similarity descending.
        Empty list if index is not built or no results above threshold.
    """
    async with _cache_lock:
        cache = _cache

    if cache is None:
        logger.debug("Vector index not built — returning empty results")
        return []

    try:
        import numpy as np
        query = np.array(query_embedding, dtype=np.float32)
        # Cosine similarity = dot product (embeddings are L2-normalized)
        scores = cache["matrix"].dot(query)
        # Get top-k indices
        top_indices = np.argsort(scores)[::-1][:top_k]

        results: list[SimilarChunk] = []
        for idx in top_indices:
            score = float(scores[idx])
            if score < min_similarity:
                break
            meta = cache["chunk_meta"][idx]
            results.append(SimilarChunk(
                chunk_id=cache["chunk_ids"][idx],
                document_id=meta["document_id"],
                chunk_text=cache["chunk_texts"][idx],
                chunk_index=meta["chunk_index"],
                page_number=meta["page_number"],
                section=meta["section"],
                similarity=round(score, 4),
                metadata=meta["metadata"],
            ))
        return results

    except Exception as exc:
        logger.error("Vector search failed", error=str(exc))
        return []


def invalidate_cache() -> None:
    """Clear the in-memory index so next query rebuilds from DB."""
    global _cache
    _cache = None
    logger.info("Vector index cache invalidated")


def index_size() -> int:
    """Return number of chunks currently in the index."""
    if _cache is None:
        return 0
    return len(_cache.get("chunk_ids", []))
