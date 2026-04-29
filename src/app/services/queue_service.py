"""Optional Redis/RQ enqueue helpers."""

from __future__ import annotations

import logging

from app.db.redis import get_redis_client

logger = logging.getLogger(__name__)


def enqueue_embedding_index(product_id: int) -> None:
    try:
        from rq import Queue

        from app.workers.jobs import index_product_embedding_job

        q = Queue("embeddings", connection=get_redis_client())
        q.enqueue(index_product_embedding_job, product_id)
    except Exception:
        logger.warning("enqueue_embedding_failed product_id=%s", product_id, exc_info=True)


def enqueue_post_checkout(order_id: str) -> None:
    """Hook for notifications/analytics after checkout (worker implements business logic)."""

    try:
        from rq import Queue

        from app.workers.jobs import post_checkout_stub

        q = Queue("post_checkout", connection=get_redis_client())
        q.enqueue(post_checkout_stub, order_id)
    except Exception:
        logger.warning("enqueue_post_checkout_failed order_id=%s", order_id, exc_info=True)


