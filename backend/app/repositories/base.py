"""
Generic async repository base class.

Every entity repository extends BaseRepository[ModelType] and gets
standard CRUD operations for free. Business-specific queries live in
the concrete subclass.

Design:
  - All methods are async — they expect an AsyncSession injected from FastAPI deps.
  - No session management here — sessions are managed at the API / service layer.
  - Soft-delete is NOT handled in the base class — models that need it define
    their own is_deleted/is_active column and the subclass overrides list/get.
"""
from __future__ import annotations

from typing import Any, Generic, Sequence, Type, TypeVar
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base
from app.core.logging import get_logger

ModelType = TypeVar("ModelType", bound=Base)

logger = get_logger(__name__)


class BaseRepository(Generic[ModelType]):
    """
    Async CRUD base repository.

    Usage:
        class UserRepository(BaseRepository[User]):
            model = User
    """

    model: Type[ModelType]  # subclass must define this

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ---------------------------------------------------------------------- #
    # Read
    # ---------------------------------------------------------------------- #

    async def get_by_id(self, entity_id: UUID) -> ModelType | None:
        """Return entity by primary key, or None if not found."""
        result = await self.db.execute(
            select(self.model).where(self.model.id == entity_id)  # type: ignore[attr-defined]
        )
        return result.scalar_one_or_none()

    async def get_by_id_or_raise(self, entity_id: UUID) -> ModelType:
        """Return entity by primary key, raises NotFoundError if missing."""
        from app.core.exceptions import NotFoundError
        entity = await self.get_by_id(entity_id)
        if entity is None:
            raise NotFoundError(self.model.__name__, str(entity_id))
        return entity

    async def list_all(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[ModelType]:
        """Return paginated list of all records (no filtering)."""
        result = await self.db.execute(
            select(self.model).offset(offset).limit(limit)
        )
        return result.scalars().all()

    async def count(self) -> int:
        """Return total count of all records."""
        result = await self.db.execute(
            select(func.count()).select_from(self.model)
        )
        return result.scalar_one()

    # ---------------------------------------------------------------------- #
    # Write
    # ---------------------------------------------------------------------- #

    async def create(self, obj: ModelType) -> ModelType:
        """
        Persist a new entity.

        The caller constructs the model instance and passes it in.
        This keeps the factory logic in the service layer.
        """
        self.db.add(obj)
        await self.db.flush()      # get server-generated values (id, timestamps)
        await self.db.refresh(obj) # reload from DB to pick up defaults
        return obj

    async def update(self, obj: ModelType, updates: dict[str, Any]) -> ModelType:
        """
        Apply a dict of updates to an existing entity and flush.

        Only fields present in `updates` are changed.
        """
        for field, value in updates.items():
            setattr(obj, field, value)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj: ModelType) -> None:
        """Hard-delete the entity. Use only when genuinely needed."""
        await self.db.delete(obj)
        await self.db.flush()
