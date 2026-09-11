"""
INSIGHT AI — FastAPI application factory.

This module creates and configures the FastAPI application instance.

Responsibilities:
  - Create the FastAPI app with metadata and OpenAPI settings
  - Register startup / shutdown lifespan handlers
  - Mount middleware (request ID, security headers)
  - Register exception handlers for domain exceptions → HTTP responses
  - Include all API routers
  - Expose the health check endpoint at /health

Import this module to get the `app` object:
    from app.main import app
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import v1_router
from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    DocumentValidationError,
    InsightAIError,
    NotFoundError,
    UnsupportedFileTypeError,
    ValidationError,
)
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware
from app.database.init_db import check_database_connection, initialize_database
from app.schemas.base import APIResponse
from app.schemas.health import HealthResponse

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Lifespan — startup and shutdown
# --------------------------------------------------------------------------- #

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle.

    Startup:
      1. Configure structured logging
      2. Initialise database (pgvector, tables in dev, seed data)

    Shutdown:
      1. Dispose SQLAlchemy engine connection pool
    """
    settings = get_settings()

    # --- Startup ---
    configure_logging(
        level=settings.log_level,
        fmt=settings.log_format,
        log_file=settings.log_file,
    )
    logger.info(
        "INSIGHT AI starting",
        version=settings.app_version,
        env=settings.app_env,
    )

    await initialize_database()

    is_db_up = await check_database_connection()
    if not is_db_up:
        logger.error("Database unreachable at startup — check DATABASE_URL")
    else:
        logger.info("Database connection verified")

    logger.info("INSIGHT AI ready", host=settings.app_host, port=settings.app_port)

    yield  # --- Application runs here ---

    # --- Shutdown ---
    from app.database.session import engine
    await engine.dispose()
    logger.info("INSIGHT AI shutdown complete")


# --------------------------------------------------------------------------- #
# Application factory
# --------------------------------------------------------------------------- #

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="INSIGHT AI — Commercial Submission Intelligence",
        description=(
            "AI-powered insurance document intelligence and underwriting support. "
            "Converts unstructured commercial submission documents into structured "
            "insights. A human underwriter retains final decision authority."
        ),
        version=settings.app_version,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # --- CORS ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Custom middleware (order matters: added last = runs first) ---
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # --- Exception handlers ---
    _register_exception_handlers(app)

    # --- Routers ---
    app.include_router(v1_router)

    # --- Health check (no auth required) ---
    @app.get(
        "/health",
        response_model=APIResponse[HealthResponse],
        tags=["Health"],
        summary="Application health check",
        include_in_schema=True,
    )
    async def health_check() -> APIResponse[HealthResponse]:
        db_status = await check_database_connection()
        from app.ingestion.ocr_service import ocr_availability_info
        from app.ai import llm_is_available
        ocr_info = ocr_availability_info()
        return APIResponse.ok(
            HealthResponse(
                status="ok" if db_status else "degraded",
                version=settings.app_version,
                environment=settings.app_env,
                database="connected" if db_status else "unreachable",
                llm_configured=settings.llm_configured,
                ocr_available=ocr_info.get("available", False),
                llm_model=settings.llm_model if settings.llm_configured else "",
            )
        )

    return app


# --------------------------------------------------------------------------- #
# Exception handlers
# --------------------------------------------------------------------------- #

def _register_exception_handlers(app: FastAPI) -> None:
    """Map domain exceptions to HTTP responses using the standard envelope."""

    @app.exception_handler(AuthenticationError)
    async def handle_auth_error(request: Request, exc: AuthenticationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=APIResponse.fail(
                code=exc.code,
                message=exc.message,
                request_id=request_id,
            ).model_dump(),
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(AuthorizationError)
    async def handle_authz_error(request: Request, exc: AuthorizationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=APIResponse.fail(
                code=exc.code,
                message=exc.message,
                request_id=request_id,
            ).model_dump(),
        )

    @app.exception_handler(NotFoundError)
    async def handle_not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=APIResponse.fail(
                code=exc.code,
                message=exc.message,
                request_id=request_id,
            ).model_dump(),
        )

    @app.exception_handler(ValidationError)
    async def handle_validation_error(request: Request, exc: ValidationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=APIResponse.fail(
                code=exc.code,
                message=exc.message,
                request_id=request_id,
            ).model_dump(),
        )

    @app.exception_handler(DocumentValidationError)
    async def handle_doc_validation(
        request: Request, exc: DocumentValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=APIResponse.fail(
                code=exc.code,
                message=exc.message,
                request_id=request_id,
            ).model_dump(),
        )

    @app.exception_handler(UnsupportedFileTypeError)
    async def handle_unsupported_file(
        request: Request, exc: UnsupportedFileTypeError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            content=APIResponse.fail(
                code=exc.code,
                message=exc.message,
                request_id=request_id,
            ).model_dump(),
        )

    @app.exception_handler(InsightAIError)
    async def handle_generic_insight_error(
        request: Request, exc: InsightAIError
    ) -> JSONResponse:
        """Catch-all for any unhandled domain exception."""
        request_id = getattr(request.state, "request_id", None)
        logger.error(
            "Unhandled domain exception",
            exc_type=type(exc).__name__,
            message=exc.message,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=APIResponse.fail(
                code=exc.code,
                message="An internal error occurred",
                request_id=request_id,
            ).model_dump(),
        )


# --------------------------------------------------------------------------- #
# Module-level app instance (used by uvicorn)
# --------------------------------------------------------------------------- #

app = create_app()
