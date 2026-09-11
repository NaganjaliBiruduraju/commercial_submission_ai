"""
DocumentRepository — data access for Document and DocumentVersion entities.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import Document, DocumentVersion
from app.repositories.base import BaseRepository
from app.core.logging import get_logger

logger = get_logger(__name__)


class DocumentRepository(BaseRepository[Document]):
    model = Document

    async def get_by_submission(
        self,
        submission_id: UUID,
        *,
        current_only: bool = True,
    ) -> list[Document]:
        """Return all documents for a submission, optionally only current versions."""
        q = select(Document).where(Document.submission_id == submission_id)
        if current_only:
            q = q.where(Document.is_current_version == True)  # noqa: E712
        q = q.order_by(Document.created_at.asc())
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def count_by_submission(self, submission_id: UUID) -> int:
        """Count current-version documents for a submission."""
        result = await self.db.execute(
            select(func.count())
            .select_from(Document)
            .where(Document.submission_id == submission_id)
            .where(Document.is_current_version == True)  # noqa: E712
        )
        return result.scalar_one()

    async def get_stored_filename_exists(self, stored_filename: str) -> bool:
        """Check if a stored filename already exists (collision guard)."""
        result = await self.db.execute(
            select(Document.id).where(Document.stored_filename == stored_filename)
        )
        return result.scalar_one_or_none() is not None

    async def mark_previous_versions(
        self, submission_id: UUID, original_filename: str
    ) -> int:
        """
        Mark all current documents with the same original_filename as
        is_current_version=False.

        Returns number of documents updated (should be 0 or 1 normally).
        Used when re-uploading a corrected document.
        """
        from sqlalchemy import update

        result = await self.db.execute(
            update(Document)
            .where(Document.submission_id == submission_id)
            .where(Document.original_filename == original_filename)
            .where(Document.is_current_version == True)  # noqa: E712
            .values(is_current_version=False)
            .returning(Document.id)
        )
        rows = result.fetchall()
        return len(rows)

    async def get_max_version_number(
        self, submission_id: UUID, original_filename: str
    ) -> int:
        """Return the highest version number for a given filename, or 0 if none."""
        result = await self.db.execute(
            select(func.max(Document.version_number))
            .where(Document.submission_id == submission_id)
            .where(Document.original_filename == original_filename)
        )
        return result.scalar_one() or 0


class DocumentVersionRepository(BaseRepository[DocumentVersion]):
    model = DocumentVersion

    async def get_versions_for_document(
        self, document_id: UUID
    ) -> list[DocumentVersion]:
        """Return all versions for a document, ordered oldest first."""
        result = await self.db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.asc())
        )
        return list(result.scalars().all())
