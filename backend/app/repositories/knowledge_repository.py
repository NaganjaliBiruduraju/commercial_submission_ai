"""
KnowledgeRepository — data access for KnowledgeDocument and KnowledgeChunk.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.repositories.base import BaseRepository
from app.core.constants import KnowledgeDocumentStatus
from app.core.logging import get_logger

logger = get_logger(__name__)


class KnowledgeDocumentRepository(BaseRepository[KnowledgeDocument]):
    model = KnowledgeDocument

    async def list_documents(
        self,
        *,
        status: str | None = None,
        category: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[KnowledgeDocument], int]:
        q = select(KnowledgeDocument)
        count_q = select(func.count()).select_from(KnowledgeDocument)

        if status:
            q = q.where(KnowledgeDocument.status == status)
            count_q = count_q.where(KnowledgeDocument.status == status)
        if category:
            q = q.where(KnowledgeDocument.category == category)
            count_q = count_q.where(KnowledgeDocument.category == category)

        total = (await self.db.execute(count_q)).scalar_one()
        docs = (await self.db.execute(
            q.order_by(KnowledgeDocument.created_at.desc())
            .offset(offset).limit(limit)
        )).scalars().all()

        return list(docs), total

    async def get_active_documents(self) -> list[KnowledgeDocument]:
        """Return all ACTIVE documents (eligible for RAG indexing)."""
        result = await self.db.execute(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.status == KnowledgeDocumentStatus.ACTIVE.value)
            .where(KnowledgeDocument.is_indexed == True)  # noqa: E712
            .order_by(KnowledgeDocument.created_at.desc())
        )
        return list(result.scalars().all())

    async def stored_filename_exists(self, filename: str) -> bool:
        result = await self.db.execute(
            select(KnowledgeDocument.id)
            .where(KnowledgeDocument.stored_filename == filename)
        )
        return result.scalar_one_or_none() is not None


class KnowledgeChunkRepository(BaseRepository[KnowledgeChunk]):
    model = KnowledgeChunk

    async def get_chunks_for_document(self, document_id: UUID) -> list[KnowledgeChunk]:
        result = await self.db.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document_id)
            .order_by(KnowledgeChunk.chunk_index.asc())
        )
        return list(result.scalars().all())

    async def delete_chunks_for_document(self, document_id: UUID) -> int:
        result = await self.db.execute(
            delete(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document_id)
            .returning(KnowledgeChunk.id)
        )
        rows = result.fetchall()
        await self.db.flush()
        return len(rows)

    async def get_all_indexed_chunks(self) -> list[KnowledgeChunk]:
        """Return all chunks from ACTIVE indexed documents (used for vector search)."""
        result = await self.db.execute(
            select(KnowledgeChunk)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(KnowledgeDocument.status == KnowledgeDocumentStatus.ACTIVE.value)
            .where(KnowledgeDocument.is_indexed == True)  # noqa: E712
            .where(KnowledgeChunk.embedding != None)  # noqa: E711
            .order_by(KnowledgeChunk.document_id, KnowledgeChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def count_for_document(self, document_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document_id)
        )
        return result.scalar_one()
