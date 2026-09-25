"""
RAG (Retrieval-Augmented Generation) layer.

Provides:
  - Embedding generation (sentence-transformers local model)
  - Vector store (in-memory numpy cosine similarity search)
  - Retrieval service (query → similar chunks → formatted context)

Usage:
    from app.rag import retrieve_context, embed_text_async, build_index

    # Retrieve knowledge for a prompt
    context = await retrieve_context(
        query="GL coverage limits for restaurants",
        top_k=5,
    )

    # Embed text for storage
    vector = await embed_text_async("Some text to embed")

    # Rebuild the vector index after new documents are indexed
    await build_index(db)
"""
from app.rag.embeddings import (
    embed_text,
    embed_batch,
    embed_text_async,
    embed_batch_async,
    chunk_text,
    embedding_model_info,
    TextChunk,
)
from app.rag.vector_store import (
    build_index,
    search,
    invalidate_cache,
    index_size,
    SimilarChunk,
)
from app.rag.retrieval import retrieve_context, retrieve_chunks

__all__ = [
    # Embeddings
    "embed_text",
    "embed_batch",
    "embed_text_async",
    "embed_batch_async",
    "chunk_text",
    "embedding_model_info",
    "TextChunk",
    # Vector store
    "build_index",
    "search",
    "invalidate_cache",
    "index_size",
    "SimilarChunk",
    # Retrieval
    "retrieve_context",
    "retrieve_chunks",
]
