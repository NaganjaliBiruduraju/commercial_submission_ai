"""
API v1 router aggregator.

All v1 routers are included here and mounted under /api/v1.
"""
from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.submissions import router as submissions_router
from app.api.v1.knowledge import router as knowledge_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(auth_router)
v1_router.include_router(users_router)
v1_router.include_router(submissions_router)
v1_router.include_router(knowledge_router)

__all__ = ["v1_router"]
