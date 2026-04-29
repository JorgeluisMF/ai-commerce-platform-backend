"""Per-request context for structured logging (request id, path, optional user id)."""

from __future__ import annotations

import contextvars
import logging
import uuid

request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id",
    default=None,
)
request_path_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_path",
    default=None,
)
request_method_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_method",
    default=None,
)
duration_ms_ctx: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "duration_ms",
    default=None,
)
user_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "user_id",
    default=None,
)


class RequestContextLogFilter(logging.Filter):
    """Attach request-scoped fields to every LogRecord for JSON output."""

    def filter(self, record: logging.LogRecord) -> bool:
        rid = request_id_ctx.get()
        record.request_id = rid if rid else "-"
        path = request_path_ctx.get()
        record.path = path if path else "-"
        method = request_method_ctx.get()
        record.method = method if method else "-"
        dur = duration_ms_ctx.get()
        record.duration_ms = round(dur, 2) if dur is not None else None
        uid = user_id_ctx.get()
        record.user_id = uid if uid else None
        return True


def new_request_id() -> str:
    return str(uuid.uuid4())
