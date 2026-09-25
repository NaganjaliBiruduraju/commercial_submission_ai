"""
Embedding service — generates vector embeddings using sentence-transformers.

Model: sentence-transformers/all-MiniLM-L6-v2
  - 384-dimensional output
  - Runs locally — no API key required, no data leaves the server
  - Good balance of speed and semantic quality for insurance text
  - ~80 MB model download on first use (cached by sentence-transformers)

Design:
  - The model is loaded once (lazy singleton) and shared across requests.
  - Encoding is synchronous (numpy/torch) — run in thread pool from async code.
  - Embeddings are L2-normalized (unit vectors) so cosine similarity = dot product.
  - Chunking: documents are split into overlapping windows before embedding.
    Each chunk is ~500 tokens / ~400 words with 50-token / ~40-word overlap.

Usage:
    # Embed a single text
    vector = embed_text("ACORD 125 general liability coverage")

    # Embed multiple texts efficiently
    vectors = embed_batch(["text1", "text2", ...])

    # Chunk a document then embed all chunks
    chunks = chunk_text(full_text, title="GL Guidelines v2")
    vectors = embed_batch([c["text"] for c in chunks])
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import EmbeddingError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Thread pool for CPU-bound embedding work
_EMBED_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="embed")

# Lazy-loaded model singleton
_model: Any = None
_model_name: str = ""

# Chunking parameters
CHUNK_SIZE_WORDS = 400      # ~500 tokens for English text
CHUNK_OVERLAP_WORDS = 40    # ~50-token overlap
MIN_CHUNK_WORDS = 20        # discard tiny trailing chunks


@dataclass
class TextChunk:
    """A single chunk ready for embedding."""
    text: str
    chunk_index: int
    page_number: int | None
    section: str | None
    metadata: dict


def _load_model() -> Any:
    """Load the sentence-transformers model (lazy, cached)."""
    global _model, _model_name
    settings = get_settings()
    model_name = settings.embedding_model

    if _model is not None and _model_name == model_name:
        return _model

    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import]
        logger.info("Loading embedding model", model=model_name)
        _model = SentenceTransformer(model_name)
        _model_name = model_name
        logger.info("Embedding model loaded", model=model_name)
        return _model
    except ImportError:
        raise EmbeddingError(
            "sentence-transformers not installed. "
            "Run: pip install sentence-transformers"
        )
    except Exception as exc:
        raise EmbeddingError(f"Failed to load embedding model '{model_name}': {exc}") from exc


def _embed_sync(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings synchronously (runs in thread pool).
    Returns L2-normalized vectors as Python lists.
    """
    model = _load_model()
    try:
        import numpy as np
        embeddings = model.encode(
            texts,
            normalize_embeddings=True,   # cosine similarity = dot product
            batch_size=32,
            show_progress_bar=False,
        )
        return [emb.tolist() for emb in embeddings]
    except Exception as exc:
        raise EmbeddingError(f"Embedding generation failed: {exc}") from exc


def embed_text(text: str) -> list[float]:
    """Synchronously embed a single text string. Use from non-async code only."""
    results = _embed_sync([text])
    return results[0]


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Synchronously embed a list of texts. Use from non-async code only."""
    if not texts:
        return []
    return _embed_sync(texts)


async def embed_text_async(text: str) -> list[float]:
    """Embed a single text asynchronously (runs in thread pool)."""
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(
        _EMBED_EXECUTOR,
        partial(_embed_sync, [text]),
    )
    return results[0]


async def embed_batch_async(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts asynchronously (runs in thread pool)."""
    if not texts:
        return []
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _EMBED_EXECUTOR,
        partial(_embed_sync, texts),
    )


def chunk_text(
    text: str,
    title: str = "",
    category: str = "",
    version: str = "",
    page_hints: dict[int, int] | None = None,  # char_offset -> page_number
) -> list[TextChunk]:
    """
    Split document text into overlapping chunks for embedding.

    Args:
        text:        Full document text.
        title:       Document title (stored in chunk metadata for RAG citation).
        category:    Document category.
        version:     Document version.
        page_hints:  Optional mapping of character offset to page number.

    Returns:
        List of TextChunk objects ready for embedding.
    """
    if not text or not text.strip():
        return []

    words = text.split()
    if len(words) < MIN_CHUNK_WORDS:
        return [TextChunk(
            text=text.strip(),
            chunk_index=0,
            page_number=None,
            section=_extract_section(text, 0),
            metadata={"title": title, "category": category, "version": version},
        )]

    chunks: list[TextChunk] = []
    start = 0
    chunk_index = 0

    while start < len(words):
        end = min(start + CHUNK_SIZE_WORDS, len(words))
        chunk_words = words[start:end]

        if len(chunk_words) < MIN_CHUNK_WORDS:
            # Too small — merge into previous chunk if possible
            if chunks:
                prev = chunks[-1]
                merged_text = prev.text + " " + " ".join(chunk_words)
                chunks[-1] = TextChunk(
                    text=merged_text,
                    chunk_index=prev.chunk_index,
                    page_number=prev.page_number,
                    section=prev.section,
                    metadata=prev.metadata,
                )
            break

        chunk_text_str = " ".join(chunk_words)
        section = _extract_section(chunk_text_str, chunk_index)

        chunks.append(TextChunk(
            text=chunk_text_str,
            chunk_index=chunk_index,
            page_number=None,   # page resolution requires richer input
            section=section,
            metadata={
                "title": title,
                "category": category,
                "version": version,
                "word_start": start,
                "word_end": end,
            },
        ))

        chunk_index += 1
        start += CHUNK_SIZE_WORDS - CHUNK_OVERLAP_WORDS  # overlap

    logger.debug(
        "Text chunked",
        title=title,
        total_words=len(words),
        chunk_count=len(chunks),
    )
    return chunks


def _extract_section(text: str, chunk_index: int) -> str | None:
    """Extract the first heading-like line from chunk text for citation."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") or stripped.startswith("## "):
            return stripped.lstrip("#").strip()
        if len(stripped) > 5 and stripped.isupper() and len(stripped) < 80:
            return stripped
    return None


def embedding_model_info() -> dict:
    """Return info about the current embedding model for health checks."""
    settings = get_settings()
    return {
        "model": settings.embedding_model,
        "dimension": settings.embedding_dimension,
        "loaded": _model is not None,
    }
