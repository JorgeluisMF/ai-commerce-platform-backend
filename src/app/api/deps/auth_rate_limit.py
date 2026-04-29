"""Redis-backed rate limiting for authentication endpoints."""

from redis.exceptions import RedisError
from starlette.requests import Request

from app.core.config import get_settings
from app.core.http_exceptions import raise_api_error
from app.db.redis import get_redis_client


def enforce_auth_rate_limit(request: Request) -> None:
    settings = get_settings()
    if not settings.auth_rate_limit_enabled:
        return

    client_ip = request.client.host if request.client else "unknown"
    key = f"auth:rl:{client_ip}"

    try:
        rc = get_redis_client()
        attempts = rc.incr(key)
        if attempts == 1:
            rc.expire(key, settings.auth_rate_limit_window_sec)
        if attempts > settings.auth_rate_limit_max_requests:
            raise_api_error(
                code="rate_limited",
                message="Too many attempts. Try again later.",
                status_code=429,
                details={"retry_after_sec": settings.auth_rate_limit_window_sec},
            )
    except RedisError:
        # Fail open when Redis is unavailable — auth remains usable without limiter state.
        return
