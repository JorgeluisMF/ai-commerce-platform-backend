"""Redis-backed idempotent response replay (JSON body + HTTP status)."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

from redis.exceptions import RedisError

if TYPE_CHECKING:
    from redis import Redis

logger = logging.getLogger(__name__)


def compute_key(user_id: uuid.UUID, raw_key: str, namespace: str) -> str:
    normalized = raw_key.strip()
    if not normalized:
        raise ValueError("idempotency key is empty")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    safe_ns = namespace.replace(":", "_")
    return f"idem:v1:{safe_ns}:{user_id}:{digest}"


def get_cached_response(redis_client: Redis, key: str) -> tuple[int, dict[str, Any]] | None:
    try:
        raw = redis_client.get(key)
        if not raw:
            return None
        obj = json.loads(raw)
        code = int(obj["status_code"])
        body = obj["body"]
        if not isinstance(body, dict):
            return None
        return code, body
    except (RedisError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        logger.warning("idempotency_cache_read_failed", extra={"key": key})
        return None


def set_cached_response(
    redis_client: Redis,
    key: str,
    *,
    status_code: int,
    body: dict[str, Any],
    ttl_sec: int,
) -> None:
    try:
        envelope = {"status_code": status_code, "body": body}
        redis_client.setex(key, ttl_sec, json.dumps(envelope, default=str))
    except RedisError:
        logger.warning("idempotency_cache_write_failed", extra={"key": key})
