"""
RAG retrieval service — semantic search over the knowledge base.

Pipeline:
  1. Embed the query using the same model as chunks (sentence-transformers).
  2. Search the vector store for top-k similar chunks.
  3. Assemble the retrieved text into a context string for the LLM.
  4. Optionally apply re-ranking or filtering.

Usage from extraction/classification/summarization:
    context = await retrieve_context(
        query="General liability coverage for restaurants",
        top_k=5,
    )
    # Pass context to the LLM prompt
"""
from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.rag.embeddings import embed_text_async
from app.rag.vector_store import SimilarChunk, build_index, search

logger = get_logger(__name__)


async def retrieve_context(
    query: str,
    top_k: int = 5,
    min_similarity: float = 0.30,
    db: Any | None = None,
    rebuild_index: bool = False,
) -> str:
    """
    Retrieve relevant knowledge chunks for a query.

    Args:
        query:          Natural language query (e.g. "GL coverage requirements").
        top_k:          Max number of chunks to retrieve.
        min_similarity: Minimum cosine similarity threshold (0.0–1.0).
        db:             Database session (required if rebuild_index=True).
        rebuild_index:  Force a rebuild of the vector index before search.

    Returns:
        Formatted context string with citations, ready to inject into a prompt.
        Empty string if no relevant chunks found.
    """
    if rebuild_index:
        if db is None:
            logger.warning("rebuild_index=True but no db provided — skipping rebuild")
        else:
            await build_index(db)

    # 1. Embed query
    query_embedding = await embed_text_async(query)

    # 2. Search
    results = await search(
        query_embedding=query_embedding,
        top_k=top_k,
        min_similarity=min_similarity,
    )

    if not results:
        logger.debug("No relevant knowledge chunks found", query=query[:100])
        return ""

    # 3. Format context
    context_parts: list[str] = []
    for i, chunk in enumerate(results, 1):
        meta = chunk.metadata
        title = meta.get("title", "Unknown Document")
        version = meta.get("version", "")
        section = chunk.section or "Section Unknown"
        page = f" (page {chunk.page_number})" if chunk.page_number else ""

        citation = f"[{i}] {title} {version}{page} — {section}"
        context_parts.append(f"{citation}\n{chunk.chunk_text}")

    context = "\n\n".join(context_parts)

    logger.info(
        "RAG context retrieved",
        query_chars=len(query),
        chunks_found=len(results),
        context_chars=len(context),
        top_similarity=results[0].similarity if results else 0.0,
    )

    return context


async def retrieve_chunks(
    query: str,
    top_k: int = 5,
    min_similarity: float = 0.30,
    db: Any | None = None,
    rebuild_index: bool = False,
) -> list[SimilarChunk]:
    """
    Retrieve similar chunks as structured objects (for API responses).

    Returns the raw SimilarChunk list instead of formatted text.
    """
    if rebuild_index and db:
        await build_index(db)

    query_embedding = await embed_text_async(query)

    results = await search(
        query_embedding=query_embedding,
        top_k=top_k,
        min_similarity=min_similarity,
    )

    logger.info(
        "Chunks retrieved",
        query_chars=len(query),
        chunks=len(results),
        top_sim=results[0].similarity if results else 0.0,
    )

    return results
