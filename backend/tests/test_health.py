"""
Test health endpoint.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Test that health endpoint returns OK status."""
    response = await client.get("/health")
    
    assert response.status_code == 200
    
    data = response.json()
    assert data["success"] is True
    assert data["data"]["status"] == "ok"
    assert "version" in data["data"]
    assert "environment" in data["data"]
    assert "database" in data["data"]


@pytest.mark.asyncio
async def test_health_response_structure(client: AsyncClient):
    """Test health endpoint response structure."""
    response = await client.get("/health")
    data = response.json()
    
    # Check APIResponse wrapper structure
    assert "success" in data
    assert "data" in data
    assert "error" in data
    assert "request_id" in data
    
    # Check health data
    health_data = data["data"]
    assert isinstance(health_data, dict)
    assert "status" in health_data
    assert "version" in health_data
    assert "environment" in health_data
    assert "database" in health_data
    assert "llm_configured" in health_data
