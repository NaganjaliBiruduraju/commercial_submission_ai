"""
Test submission API endpoints.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, Role
from app.models.submission import Submission
from app.core.security import hash_password
from app.core.constants import UserRole


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user."""
    # Create role if not exists
    from sqlalchemy import select
    result = await db_session.execute(
        select(Role).where(Role.name == UserRole.UNDERWRITER.value)
    )
    role = result.scalar_one_or_none()
    
    if not role:
        role = Role(name=UserRole.UNDERWRITER.value, description="Underwriter")
        db_session.add(role)
        await db_session.flush()
    
    user = User(
        email="test@example.com",
        hashed_password=hash_password("testpassword123"),
        full_name="Test User",
        role_id=role.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    return user


@pytest.fixture
async def auth_headers(client: AsyncClient, test_user):
    """Get authentication headers."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "testpassword123",
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    token = data["data"]["access_token"]
    
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_submission(
    client: AsyncClient,
    auth_headers: dict,
    sample_submission_data: dict,
):
    """Test creating a new submission."""
    response = await client.post(
        "/api/v1/submissions",
        json=sample_submission_data,
        headers=auth_headers,
    )
    
    assert response.status_code == 201
    data = response.json()
    
    assert data["success"] is True
    assert "id" in data["data"]
    assert data["data"]["applicant_name"] == sample_submission_data["applicant_name"]
    assert data["data"]["lob"] == sample_submission_data["lob"]


@pytest.mark.asyncio
async def test_list_submissions(client: AsyncClient, auth_headers: dict):
    """Test listing submissions."""
    response = await client.get(
        "/api/v1/submissions",
        headers=auth_headers,
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["success"] is True
    assert "submissions" in data["data"]
    assert "total" in data["data"]
    assert isinstance(data["data"]["submissions"], list)


@pytest.mark.asyncio
async def test_submission_requires_auth(client: AsyncClient):
    """Test that submission endpoints require authentication."""
    response = await client.get("/api/v1/submissions")
    
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
