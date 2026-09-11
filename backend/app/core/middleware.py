"""
FastAPI middleware.

Middleware runs on every request before it reaches a route handler.
Two middlewares are defined here:

1. RequestIDMiddleware:
   - Generates a unique UUID for every request
   - Attaches it to the request state and response headers
   - Sets it in the logging context variables so all log entries for
     this request carry the same request_id for correlation
   - Injects request_id into every JSON response

2. SecurityHeadersMiddleware:
   - Adds standard HTTP security headers to every response
   - Prevents common web vulnerabilities (clickjacking, MIME sniffing, XSS)
   - In production, HSTS is enabled
"""
from __future__ import annotations

import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging import get_logger, set_log_context

logger = get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Attach a unique request_id to every request and response.

    The request_id is:
    - Stored in request.state.request_id
    - Added to the X-Request-ID response header
    - Set in the logging context so all log entries for this request
      include the same request_id for easy log correlation
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: object) -> Response:
        # Accept an existing request ID from a load balancer/proxy, or generate one
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        # Set the context variable so all loggers in this request see this ID
        set_log_context(request_id=request_id)

        response: Response = await call_next(request)  # type: ignore[operator]
        response.headers["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add HTTP security headers to every response.

    Headers applied:
    - X-Content-Type-Options: nosniff
        Prevents browsers from MIME-sniffing away from the declared content type
    - X-Frame-Options: DENY
        Prevents the app from being embedded in iframes (clickjacking protection)
    - X-XSS-Protection: 1; mode=block
        Legacy XSS filter for older browsers
    - Referrer-Policy: strict-origin-when-cross-origin
        Limits referrer information sent to third parties
    - Permissions-Policy: geolocation=(), microphone=(), camera=()
        Disables browser features not used by this application
    - Content-Security-Policy: (restrictive default)
        Prevents injection of unauthorized scripts
    """

    def __init__(self, app: ASGIApp, is_production: bool = False) -> None:
        super().__init__(app)
        self._is_production = is_production

    async def dispatch(self, request: Request, call_next: object) -> Response:
        response: Response = await call_next(request)  # type: ignore[operator]

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )

        if self._is_production:
            # Only add HSTS in production — prevents locking out development
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        return response
