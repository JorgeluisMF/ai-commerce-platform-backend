from __future__ import annotations

import hashlib
import json
import logging

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.schemas.rag import RAGAnswerResponse

logger = logging.getLogger(__name__)
_RAG_HISTORY_MAX_TURNS = 4


def _cache_key(*, question: str, top_k: int, is_active: bool | None) -> str:
    payload = f"{question.strip().lower()}|{top_k}|{is_active}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"rag:answer:{digest}"


def get_cached_rag_response(
    redis_client: Redis,
    *,
    question: str,
    top_k: int,
    is_active: bool | None,
) -> RAGAnswerResponse | None:
    settings = get_settings()
    if not settings.rag_cache_enabled:
        return None

    try:
        key = _cache_key(question=question, top_k=top_k, is_active=is_active)
        raw = redis_client.get(key)
        if not raw:
            return None
        return RAGAnswerResponse.model_validate_json(raw)
    except (RedisError, json.JSONDecodeError, ValueError):
        logger.exception("Failed to read RAG cache.")
        return None


def cache_rag_response(
    redis_client: Redis,
    *,
    question: str,
    top_k: int,
    is_active: bool | None,
    response: RAGAnswerResponse,
) -> None:
    settings = get_settings()
    if not settings.rag_cache_enabled:
        return

    try:
        key = _cache_key(question=question, top_k=top_k, is_active=is_active)
        redis_client.setex(key, settings.rag_cache_ttl_sec, response.model_dump_json())
    except RedisError:
        logger.exception("Failed to write RAG cache.")


def enforce_rag_rate_limit(redis_client: Redis, *, client_id: str) -> tuple[bool, int]:
    settings = get_settings()
    if not settings.rag_rate_limit_enabled:
        return True, settings.rag_rate_limit_max_requests

    key = f"rag:rate:{client_id}"
    try:
        current = redis_client.incr(key)
        if current == 1:
            redis_client.expire(key, settings.rag_rate_limit_window_sec)
        remaining = max(settings.rag_rate_limit_max_requests - int(current), 0)
        allowed = int(current) <= settings.rag_rate_limit_max_requests
        return allowed, remaining
    except RedisError:
        logger.exception("Rate limit check failed; allowing request.")
        # Fail-open strategy to keep API available if Redis has transient issues.
        return True, settings.rag_rate_limit_max_requests


def _history_key(*, client_id: str) -> str:
    return f"rag:history:{client_id}"


def get_rag_history(redis_client: Redis, *, client_id: str) -> list[dict]:
    settings = get_settings()
    key = _history_key(client_id=client_id)
    try:
        raw = redis_client.get(key)
        if not raw:
            return []
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]
    except (RedisError, json.JSONDecodeError, ValueError):
        logger.exception("Failed to read RAG history.")
        return []


def append_rag_history(
    redis_client: Redis,
    *,
    client_id: str,
    question: str,
    answer: str,
) -> None:
    settings = get_settings()
    key = _history_key(client_id=client_id)
    try:
        history = get_rag_history(redis_client, client_id=client_id)
        history.append({"question": question.strip(), "answer": answer.strip()})
        history = history[-_RAG_HISTORY_MAX_TURNS:]
        redis_client.setex(key, settings.rag_cache_ttl_sec * 10, json.dumps(history))
    except RedisError:
        logger.exception("Failed to write RAG history.")
