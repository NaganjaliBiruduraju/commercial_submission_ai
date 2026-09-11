"""Health check response schema."""
from __future__ import annotations
from app.schemas.base import InsightBaseModel


class HealthResponse(InsightBaseModel):
    status: str
    version: str
    environment: str
    database: str
    llm_configured: bool
    ocr_available: bool = False
    llm_model: str = ""
