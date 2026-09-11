"""
UserService — user lifecycle management (CRUD + password changes).

Called from API routers. All business rules enforced here.
No HTTP / FastAPI imports.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import UserRole
from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.user_repository import RoleRepository, UserRepository
from app.schemas.user import (
    RoleResponse,
    UserCreate,
    UserPasswordChange,
    UserResponse,
    UserSummary,
    UserUpdate,
)

logger = get_logger(__name__)


def _to_user_response(user: User) -> UserResponse:
    """Map ORM User → UserResponse schema. Role must be loaded."""
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        last_login=user.last_login,
        created_at=user.created_at,
        updated_at=user.updated_at,
        role=RoleResponse(
            id=user.role.id,
            name=user.role.name,
            description=user.role.description,
            created_at=user.role.created_at,
            updated_at=user.role.updated_at,
        ),
    )


def _to_user_summary(user: User) -> UserSummary:
    return UserSummary(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role_name=user.role.name if user.role else "",
    )


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.role_repo = RoleRepository(db)

    # ---------------------------------------------------------------------- #
    # Read
    # ---------------------------------------------------------------------- #

    async def get_user(self, user_id: UUID) -> UserResponse:
        user = await self.user_repo.get_by_id_with_role(user_id)
        if user is None:
            raise NotFoundError("User", str(user_id))
        return _to_user_response(user)

    async def get_me(self, user_id: UUID) -> UserResponse:
        """Return the calling user's own profile."""
        return await self.get_user(user_id)

    async def list_users(
        self,
        *,
        is_active: bool | None = None,
        role_name: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[UserResponse], int]:
        offset = (page - 1) * page_size
        users, total = await self.user_repo.list_users(
            is_active=is_active,
            role_name=role_name,
            offset=offset,
            limit=page_size,
        )
        return [_to_user_response(u) for u in users], total

    # ---------------------------------------------------------------------- #
    # Write
    # ---------------------------------------------------------------------- #

    async def create_user(
        self, payload: UserCreate, created_by_id: UUID
    ) -> UserResponse:
        """
        Create a new user. Admin only (enforced at router level).

        Raises:
            ValidationError: Email already registered.
            NotFoundError: Requested role does not exist in DB.
        """
        if await self.user_repo.email_exists(payload.email):
            raise ValidationError(f"Email '{payload.email}' is already registered")

        role = await self.role_repo.get_by_name(payload.role.value)
        if role is None:
            raise NotFoundError("Role", payload.role.value)

        new_user = User(
            email=payload.email.lower().strip(),
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
            role_id=role.id,
            is_active=True,
            created_by=created_by_id,
        )
        user = await self.user_repo.create(new_user)
        # Reload with role
        user = await self.user_repo.get_by_id_with_role(user.id)
        await self.db.commit()

        logger.info(
            "User created",
            new_user_id=str(user.id),  # type: ignore[union-attr]
            role=payload.role.value,
            created_by=str(created_by_id),
        )
        return _to_user_response(user)  # type: ignore[arg-type]

    async def update_user(
        self, user_id: UUID, payload: UserUpdate, acting_user_id: UUID
    ) -> UserResponse:
        """
        Update a user's profile. Admin can update any user.
        A user can only update their own full_name.
        Role/active status changes require ADMIN.
        """
        user = await self.user_repo.get_by_id_with_role(user_id)
        if user is None:
            raise NotFoundError("User", str(user_id))

        updates: dict = {}

        if payload.full_name is not None:
            updates["full_name"] = payload.full_name

        if payload.is_active is not None:
            updates["is_active"] = payload.is_active

        if payload.role is not None:
            role = await self.role_repo.get_by_name(payload.role.value)
            if role is None:
                raise NotFoundError("Role", payload.role.value)
            updates["role_id"] = role.id

        if updates:
            user = await self.user_repo.update(user, updates)
            await self.db.commit()
            user = await self.user_repo.get_by_id_with_role(user_id)

        logger.info("User updated", user_id=str(user_id), by=str(acting_user_id))
        return _to_user_response(user)  # type: ignore[arg-type]

    async def change_password(
        self, user_id: UUID, payload: UserPasswordChange
    ) -> None:
        """
        Let a user change their own password.

        Raises:
            AuthorizationError: Current password is wrong.
        """
        user = await self.user_repo.get_by_id_or_raise(user_id)

        if not verify_password(payload.current_password, user.hashed_password):
            raise AuthorizationError("Current password is incorrect")

        if payload.current_password == payload.new_password:
            raise ValidationError("New password must differ from the current one")

        await self.user_repo.update(user, {"hashed_password": hash_password(payload.new_password)})
        await self.db.commit()

        logger.info("Password changed", user_id=str(user_id))

    async def deactivate_user(self, user_id: UUID, acting_user_id: UUID) -> None:
        """Soft-deactivate a user. Admin only (enforced at router)."""
        user = await self.user_repo.get_by_id_or_raise(user_id)
        if str(user_id) == str(acting_user_id):
            raise ValidationError("You cannot deactivate your own account")
        await self.user_repo.update(user, {"is_active": False})
        await self.db.commit()
        logger.info("User deactivated", user_id=str(user_id), by=str(acting_user_id))
