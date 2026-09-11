"""
SubmissionRepository — data access layer for Submission entities.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.submission import Submission
from app.models.user import User
from app.repositories.base import BaseRepository
from app.core.constants import SubmissionStatus
from app.core.logging import get_logger

logger = get_logger(__name__)


class SubmissionRepository(BaseRepository[Submission]):
    model = Submission

    async def get_with_relations(self, submission_id: UUID) -> Submission | None:
        """Return submission with documents, assigned underwriter, and creator loaded."""
        result = await self.db.execute(
            select(Submission)
            .options(
                selectinload(Submission.documents),
                selectinload(Submission.assigned_underwriter),
                selectinload(Submission.creator),
            )
            .where(Submission.id == submission_id)
        )
        return result.scalar_one_or_none()

    async def get_by_submission_number(
        self, submission_number: str
    ) -> Submission | None:
        result = await self.db.execute(
            select(Submission).where(
                Submission.submission_number == submission_number
            )
        )
        return result.scalar_one_or_none()

    async def list_submissions(
        self,
        *,
        status: SubmissionStatus | None = None,
        assigned_to: UUID | None = None,
        created_by: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ):
        """
        Paginated submission list with optional filters.

        Returns (submissions, total_count).
        """
        q = select(Submission).options(
            selectinload(Submission.assigned_underwriter),
            selectinload(Submission.creator),
        )
        count_q = select(func.count()).select_from(Submission)

        if status is not None:
            q = q.where(Submission.status == status.value)
            count_q = count_q.where(Submission.status == status.value)

        if assigned_to is not None:
            q = q.where(Submission.assigned_to == assigned_to)
            count_q = count_q.where(Submission.assigned_to == assigned_to)

        if created_by is not None:
            q = q.where(Submission.created_by == created_by)
            count_q = count_q.where(Submission.created_by == created_by)

        total_result = await self.db.execute(count_q)
        total = total_result.scalar_one()

        subs_result = await self.db.execute(
            q.order_by(Submission.created_at.desc()).offset(offset).limit(limit)
        )
        submissions = subs_result.scalars().all()

        return submissions, total

    async def get_next_submission_number(self) -> str:
        """
        Generate the next sequential submission number: SUB-YYYYMMDD-NNNN.

        Count is scoped to today to keep numbers short and readable.
        """
        from datetime import date
        today_str = date.today().strftime("%Y%m%d")
        prefix = f"SUB-{today_str}-"

        result = await self.db.execute(
            select(func.count())
            .select_from(Submission)
            .where(Submission.submission_number.like(f"{prefix}%"))
        )
        today_count = result.scalar_one()
        return f"{prefix}{today_count + 1:04d}"
