"""Redis fixed-window rate limit: rl:{client_ip}:{route_key}."""

from __future__ import annotations

from redis.exceptions import RedisError
from starlette.requests import Request

from app.core.config import get_settings
from app.core.http_exceptions import raise_api_error
from app.db.redis import get_redis_client
from app.services.audit_service import client_ip_from_request


def enforce_global_rate_limit(route_key: str):
    """Return an async dependency that limits requests per IP for this route group."""

    async def _limit(request: Request) -> None:
        settings = get_settings()
        if not settings.global_rate_limit_enabled:
            return
        ip = client_ip_from_request(request) or "unknown"
        key = f"rl:{ip}:{route_key}"
        try:
            rc = get_redis_client()
            attempts = rc.incr(key)
            if attempts == 1:
                rc.expire(key, settings.global_rate_limit_window_sec)
            if attempts > settings.global_rate_limit_max_requests:
                raise_api_error(
                    code="rate_limited",
                    message="Too many requests. Try again later.",
                    status_code=429,
                    details={"retry_after_sec": settings.global_rate_limit_window_sec},
                )
        except RedisError:
            return

    _limit.__name__ = f"global_rate_limit_{route_key}"
    return _limit
