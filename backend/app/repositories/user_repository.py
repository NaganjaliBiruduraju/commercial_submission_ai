"""
UserRepository — data access layer for User and Role entities.

All queries involving users go through here. No raw SQL outside this file.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import Role, User
from app.repositories.base import BaseRepository
from app.core.logging import get_logger

logger = get_logger(__name__)


class RoleRepository(BaseRepository[Role]):
    model = Role

    async def get_by_name(self, name: str) -> Role | None:
        """Return role by name (case-sensitive), or None."""
        result = await self.db.execute(
            select(Role).where(Role.name == name)
        )
        return result.scalar_one_or_none()

    async def get_by_name_or_raise(self, name: str) -> Role:
        from app.core.exceptions import NotFoundError
        role = await self.get_by_name(name)
        if role is None:
            raise NotFoundError("Role", name)
        return role


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        """
        Look up a user by email (case-insensitive).

        The email column stores lowercase values. We normalise the query
        here so the caller doesn't have to remember.
        """
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.role))
            .where(User.email == email.lower().strip())
        )
        return result.scalar_one_or_none()

    async def get_by_email_or_raise(self, email: str) -> User:
        from app.core.exceptions import NotFoundError
        user = await self.get_by_email(email)
        if user is None:
            raise NotFoundError("User", email)
        return user

    async def get_by_id_with_role(self, user_id: UUID) -> User | None:
        """Return user with role eagerly loaded."""
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.role))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        """Return True if the email is already registered."""
        result = await self.db.execute(
            select(User.id).where(User.email == email.lower().strip())
        )
        return result.scalar_one_or_none() is not None

    async def list_users(
        self,
        *,
        is_active: bool | None = None,
        role_name: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ):
        """
        List users with optional active/role filters.

        Returns (users, total_count) tuple.
        """
        from sqlalchemy import func

        q = select(User).options(selectinload(User.role))
        count_q = select(func.count()).select_from(User)

        if is_active is not None:
            q = q.where(User.is_active == is_active)
            count_q = count_q.where(User.is_active == is_active)

        if role_name is not None:
            q = q.join(User.role).where(Role.name == role_name)
            count_q = count_q.join(User.role).where(Role.name == role_name)

        total_result = await self.db.execute(count_q)
        total = total_result.scalar_one()

        users_result = await self.db.execute(
            q.order_by(User.created_at.desc()).offset(offset).limit(limit)
        )
        users = users_result.scalars().all()

        return users, total
