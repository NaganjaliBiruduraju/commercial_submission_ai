"""
KnowledgeService — admin knowledge base management.

Handles:
  - Upload of underwriting guidelines (PDF, DOCX, TXT)
  - Text extraction (using existing OCR/parsing pipeline)
  - Chunking + embedding generation
  - Persistence of KnowledgeDocument + KnowledgeChunk records
  - Index rebuild after new documents are added
  - Approval/activation workflow

Only ACTIVE documents are indexed and used for RAG.
Re-indexing a document deletes old chunks and replaces them.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import KnowledgeDocumentStatus
from app.core.exceptions import DocumentParsingError
from app.core.logging import get_logger
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.rag import chunk_text, embed_batch_async, build_index, invalidate_cache
from app.repositories.knowledge_repository import (
    KnowledgeChunkRepository,
    KnowledgeDocumentRepository,
)

logger = get_logger(__name__)


class KnowledgeService:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.doc_repo = KnowledgeDocumentRepository(db)
        self.chunk_repo = KnowledgeChunkRepository(db)

    async def upload_document(
        self,
        uploaded_file: bytes,
        original_filename: str,
        mime_type: str,
        title: str,
        category: str,
        version: str,
        uploaded_by: UUID,
        description: str | None = None,
        effective_date: str | None = None,
        expiration_date: str | None = None,
    ) -> KnowledgeDocument:
        """
        Upload a new knowledge document (DRAFT status by default).

        File is saved to KNOWLEDGE_UPLOAD_DIR.
        Text extraction and indexing happen in separate steps.
        """
        settings = get_settings()
        upload_dir = Path(settings.knowledge_upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        ext = Path(original_filename).suffix
        stored_filename = f"{uuid.uuid4()}{ext}"
        file_path = upload_dir / stored_filename

        # Save file
        file_path.write_bytes(uploaded_file)

        doc = KnowledgeDocument(
            title=title,
            category=category,
            version=version,
            effective_date=effective_date,
            expiration_date=expiration_date,
            description=description,
            status=KnowledgeDocumentStatus.DRAFT.value,
            uploaded_by=uploaded_by,
            stored_filename=stored_filename,
            original_filename=original_filename,
            mime_type=mime_type,
            file_size_bytes=len(uploaded_file),
            is_indexed=False,
        )
        self.db.add(doc)
        await self.db.flush()

        logger.info(
            "Knowledge document uploaded",
            doc_id=str(doc.id),
            title=title,
            filename=original_filename,
        )
        return doc

    async def approve_document(
        self, document_id: UUID, approved_by: UUID
    ) -> KnowledgeDocument:
        """
        Approve a document and activate it.

        Once ACTIVE, the document is indexed and used for RAG.
        """
        doc = await self.doc_repo.get_by_id_or_raise(document_id)

        doc.status = KnowledgeDocumentStatus.ACTIVE.value
        doc.approved_by = approved_by
        await self.db.flush()

        # Trigger indexing
        await self.index_document(document_id)

        logger.info(
            "Knowledge document approved and indexed",
            doc_id=str(document_id),
            title=doc.title,
        )
        return doc

    async def index_document(self, document_id: UUID) -> int:
        """
        Extract text, chunk, embed, and store chunks for a document.

        Returns number of chunks created.
        """
        doc = await self.doc_repo.get_by_id_or_raise(document_id)
        settings = get_settings()
        file_path = Path(settings.knowledge_upload_dir) / doc.stored_filename

        if not file_path.exists():
            raise DocumentParsingError(f"File not found: {doc.stored_filename}")

        # Extract text
        text = await self._extract_text(file_path, doc.mime_type)

        if not text.strip():
            logger.warning("No text extracted from document", doc_id=str(document_id))
            doc.is_indexed = False
            doc.chunk_count = 0
            await self.db.flush()
            return 0

        # Delete existing chunks
        await self.chunk_repo.delete_chunks_for_document(document_id)

        # Chunk text
        chunks = chunk_text(
            text=text,
            title=doc.title,
            category=doc.category,
            version=doc.version,
        )

        if not chunks:
            logger.warning("No chunks created", doc_id=str(document_id))
            doc.is_indexed = False
            doc.chunk_count = 0
            await self.db.flush()
            return 0

        # Embed all chunks
        chunk_texts = [c.text for c in chunks]
        embeddings = await embed_batch_async(chunk_texts)

        # Persist chunks
        for chunk, embedding in zip(chunks, embeddings):
            chunk_rec = KnowledgeChunk(
                document_id=document_id,
                chunk_text=chunk.text,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                section=chunk.section,
                embedding=embedding,
                embedding_model=settings.embedding_model,
                chunk_metadata={
                    "title": doc.title,
                    "category": doc.category,
                    "version": doc.version,
                    "effective_date": str(doc.effective_date) if doc.effective_date else None,
                },
            )
            self.db.add(chunk_rec)

        await self.db.flush()

        # Update document
        doc.is_indexed = True
        doc.chunk_count = len(chunks)
        await self.db.flush()

        # Invalidate vector store cache
        invalidate_cache()

        logger.info(
            "Document indexed",
            doc_id=str(document_id),
            chunk_count=len(chunks),
        )

        return len(chunks)

    async def rebuild_index(self) -> int:
        """
        Rebuild the in-memory vector index from all ACTIVE indexed documents.
        Returns number of chunks indexed.
        """
        count = await build_index(self.db)
        logger.info("Vector index rebuilt", chunk_count=count)
        return count

    async def delete_document(self, document_id: UUID) -> None:
        """
        Delete a knowledge document and all its chunks.
        Invalidates the vector index cache.
        """
        doc = await self.doc_repo.get_by_id_or_raise(document_id)
        settings = get_settings()
        file_path = Path(settings.knowledge_upload_dir) / doc.stored_filename

        # Delete file
        if file_path.exists():
            file_path.unlink()

        # Delete chunks (CASCADE via FK)
        await self.db.delete(doc)
        await self.db.flush()

        invalidate_cache()

        logger.info("Knowledge document deleted", doc_id=str(document_id))

    async def list_documents(
        self,
        status: str | None = None,
        category: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[KnowledgeDocument], int]:
        """List knowledge documents with pagination."""
        return await self.doc_repo.list_documents(
            status=status,
            category=category,
            offset=offset,
            limit=limit,
        )

    # ---------------------------------------------------------------------- #
    # Private helpers
    # ---------------------------------------------------------------------- #

    async def _extract_text(self, file_path: Path, mime_type: str) -> str:
        """
        Extract text from a knowledge document file.

        Uses the existing OCR/parsing layer for PDFs.
        For plain text files, reads directly.
        For Word docs, uses python-docx if available.
        """
        if mime_type == "text/plain":
            return file_path.read_text(encoding="utf-8", errors="ignore")

        if mime_type == "application/pdf":
            # Use existing PDF parser
            from app.ingestion.pdf_parser import PDFParser
            parser = PDFParser()
            pages = await parser.parse_pdf_async(str(file_path))
            return "\n\n".join(p.text for p in pages if p.text)

        if mime_type in (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        ):
            try:
                from docx import Document  # type: ignore[import]
                doc = Document(file_path)
                return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
            except ImportError:
                raise DocumentParsingError(
                    "python-docx not installed. Run: pip install python-docx"
                )

        raise DocumentParsingError(f"Unsupported mime type for extraction: {mime_type}")
