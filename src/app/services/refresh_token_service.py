"""Opaque refresh tokens stored in Redis."""

from __future__ import annotations

import hashlib
import secrets
import uuid

from redis.exceptions import RedisError

from app.core.config import Settings, get_settings


def _redis_key(raw_token: str, *, prefix: str = "refresh:v1") -> str:
    digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def ttl_seconds(settings: Settings) -> int:
    return settings.jwt_refresh_expire_days * 86400


def _refresh_token_digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _refresh_by_user_key(user_id: uuid.UUID) -> str:
    return f"refresh_by_user:{user_id}"


def issue_refresh_token(
    redis_client,
    *,
    user_id: uuid.UUID,
    settings: Settings | None = None,
) -> tuple[str, int]:
    settings = settings or get_settings()
    raw = secrets.token_urlsafe(48)
    ttl = ttl_seconds(settings)
    redis_client.setex(
        _redis_key(raw),
        ttl,
        str(user_id),
    )
    digest = _refresh_token_digest(raw)
    idx = _refresh_by_user_key(user_id)
    redis_client.sadd(idx, digest)
    redis_client.expire(idx, ttl)
    return raw, ttl


def read_refresh_token_user_id(redis_client, *, raw_token: str) -> uuid.UUID | None:
    """Return user id if token exists; does not delete (used before rotation)."""
    try:
        uid_str = redis_client.get(_redis_key(raw_token))
    except RedisError:
        return None
    if not uid_str:
        return None
    try:
        return uuid.UUID(uid_str)
    except ValueError:
        return None


def delete_refresh_token(redis_client, *, raw_token: str) -> None:
    try:
        key = _redis_key(raw_token)
        uid_str = redis_client.get(key)
        redis_client.delete(key)
        if uid_str:
            try:
                uid = uuid.UUID(uid_str)
            except ValueError:
                uid = None
            if uid is not None:
                redis_client.srem(_refresh_by_user_key(uid), _refresh_token_digest(raw_token))
    except RedisError:
        pass


def revoke_refresh_token(redis_client, *, raw_token: str) -> None:
    delete_refresh_token(redis_client, raw_token=raw_token)


def revoke_all_refresh_tokens_for_user(redis_client, *, user_id: uuid.UUID) -> int:
    """Invalidate every refresh token issued for this user (logout-all)."""
    idx = _refresh_by_user_key(user_id)
    try:
        digests = redis_client.smembers(idx)
        if not digests:
            redis_client.delete(idx)
            return 0
        pipe = redis_client.pipeline()
        for d in digests:
            pipe.delete(f"refresh:v1:{d}")
        pipe.delete(idx)
        pipe.execute()
        return len(digests)
    except RedisError:
        return 0
