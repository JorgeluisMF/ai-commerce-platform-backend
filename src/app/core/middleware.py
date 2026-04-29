"""HTTP middlewares: security headers and request tracing."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.core.request_context import (
    duration_ms_ctx,
    new_request_id,
    request_id_ctx,
    request_method_ctx,
    request_path_ctx,
)

logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign X-Request-ID, measure latency, expose structured logging context."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get("x-request-id")
        rid = (incoming.strip() if incoming else "") or new_request_id()
        tok_id = request_id_ctx.set(rid)
        tok_path = request_path_ctx.set(request.url.path)
        tok_method = request_method_ctx.set(request.method)
        tok_dur = duration_ms_ctx.set(None)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            duration_ms_ctx.set(elapsed_ms)
            logger.info(
                "http_request",
                extra={
                    "request_id": rid,
                    "path": request.url.path,
                    "method": request.method,
                    "duration_ms": round(elapsed_ms, 2),
                },
            )
            request_id_ctx.reset(tok_id)
            request_path_ctx.reset(tok_path)
            request_method_ctx.reset(tok_method)
            duration_ms_ctx.reset(tok_dur)

        response.headers["X-Request-ID"] = rid
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds baseline security headers to every response."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        settings = get_settings()
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = settings.security_x_frame_options
        response.headers["Referrer-Policy"] = settings.security_referrer_policy
        return response
