"""Forgot-password tokens in Redis (no SMTP in MVP)."""

from __future__ import annotations

import hashlib
import secrets
import uuid

from redis.exceptions import RedisError

from app.core.config import Settings, get_settings


RESET_PREFIX = "pwdreset:v1"


def _key(raw_token: str) -> str:
    digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    return f"{RESET_PREFIX}:{digest}"


def ttl_seconds(settings: Settings) -> int:
    return settings.password_reset_ttl_sec


def issue_reset_token(
    redis_client,
    *,
    user_id: uuid.UUID,
    settings: Settings | None = None,
) -> tuple[str, int]:
    settings = settings or get_settings()
    raw = secrets.token_urlsafe(32)
    redis_client.setex(_key(raw), ttl_seconds(settings), str(user_id))
    return raw, ttl_seconds(settings)


def consume_reset_token(
    redis_client,
    *,
    raw_token: str,
    settings: Settings | None = None,
) -> uuid.UUID | None:
    settings = settings or get_settings()
    key = _key(raw_token)
    try:
        pipe = redis_client.pipeline()
        pipe.get(key)
        pipe.delete(key)
        uid_str, _ = pipe.execute()
    except RedisError:
        return None
    if not uid_str:
        return None
    try:
        return uuid.UUID(uid_str)
    except ValueError:
        return None
