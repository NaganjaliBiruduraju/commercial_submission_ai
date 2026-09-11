"""
Users router — /api/v1/users

Endpoints:
  GET    /            — list users (admin only)
  POST   /            — create user (admin only)
  GET    /{user_id}   — get user by ID (admin or self)
  PATCH  /{user_id}   — update user (admin only for role/active; self for full_name)
  DELETE /{user_id}   — deactivate user (admin only)
  POST   /{user_id}/change-password  — change own password (self only)

RBAC enforced at route level via AdminDep / CurrentUser.
No business logic here — delegates to UserService.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import AdminDep, CurrentUser, DatabaseDep
from app.core.exceptions import AuthorizationError
from app.schemas.base import APIResponse, PaginatedResponse
from app.schemas.user import (
    UserCreate,
    UserPasswordChange,
    UserResponse,
    UserUpdate,
)
from app.services.user_service import UserService
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "",
    response_model=APIResponse[PaginatedResponse[UserResponse]],
    summary="List all users (admin only)",
)
async def list_users(
    current_user: AdminDep,
    db: DatabaseDep,
    is_active: bool | None = Query(default=None, description="Filter by active status"),
    role_name: str | None = Query(default=None, description="Filter by role name"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> APIResponse[PaginatedResponse[UserResponse]]:
    svc = UserService(db)
    users, total = await svc.list_users(
        is_active=is_active,
        role_name=role_name,
        page=page,
        page_size=page_size,
    )
    paginated = PaginatedResponse.create(
        items=users,
        total=total,
        page=page,
        page_size=page_size,
    )
    return APIResponse.ok(paginated)


@router.post(
    "",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user (admin only)",
)
async def create_user(
    payload: UserCreate,
    current_user: AdminDep,
    db: DatabaseDep,
) -> APIResponse[UserResponse]:
    svc = UserService(db)
    user = await svc.create_user(payload, created_by_id=current_user.id)
    return APIResponse.ok(user)


@router.get(
    "/{user_id}",
    response_model=APIResponse[UserResponse],
    summary="Get user by ID (admin or self)",
)
async def get_user(
    user_id: UUID,
    current_user: CurrentUser,
    db: DatabaseDep,
) -> APIResponse[UserResponse]:
    # Admin can see any user; non-admin can only see themselves
    role_name = current_user.role.name if current_user.role else ""
    if role_name != "ADMIN" and current_user.id != user_id:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own profile",
        )
    svc = UserService(db)
    user = await svc.get_user(user_id)
    return APIResponse.ok(user)


@router.patch(
    "/{user_id}",
    response_model=APIResponse[UserResponse],
    summary="Update user (admin only for role/active; self for full_name)",
)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    current_user: CurrentUser,
    db: DatabaseDep,
) -> APIResponse[UserResponse]:
    role_name = current_user.role.name if current_user.role else ""

    # Non-admins may only update their own full_name
    if role_name != "ADMIN":
        if current_user.id != user_id:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own profile",
            )
        # Strip privileged fields for non-admins
        payload = UserUpdate(full_name=payload.full_name)

    svc = UserService(db)
    user = await svc.update_user(user_id, payload, acting_user_id=current_user.id)
    return APIResponse.ok(user)


@router.delete(
    "/{user_id}",
    response_model=APIResponse[None],
    summary="Deactivate user (admin only — soft delete)",
)
async def deactivate_user(
    user_id: UUID,
    current_user: AdminDep,
    db: DatabaseDep,
) -> APIResponse[None]:
    svc = UserService(db)
    await svc.deactivate_user(user_id, acting_user_id=current_user.id)
    return APIResponse.ok(None)


@router.post(
    "/{user_id}/change-password",
    response_model=APIResponse[None],
    summary="Change own password",
)
async def change_password(
    user_id: UUID,
    payload: UserPasswordChange,
    current_user: CurrentUser,
    db: DatabaseDep,
) -> APIResponse[None]:
    # Users can only change their own password
    if current_user.id != user_id:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only change your own password",
        )
    svc = UserService(db)
    await svc.change_password(user_id, payload)
    return APIResponse.ok(None)
