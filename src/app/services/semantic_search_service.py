from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.embeddings import build_product_embedding_text, generate_embedding
from app.core.config import get_settings
from app.models.product import Product

logger = logging.getLogger(__name__)


class EmbeddingsStoreNotReadyError(Exception):
    pass


def _vector_to_pg_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def index_product_embedding(db: Session, product: Product) -> None:
    settings = get_settings()
    if not settings.embeddings_enabled or settings.app_env == "test":
        return

    source_text = build_product_embedding_text(
        name=product.name,
        description=product.description,
        sku=product.sku,
    )
    vector = generate_embedding(source_text)
    vector_literal = _vector_to_pg_literal(vector)

    query = text(
        """
        INSERT INTO product_embeddings (product_id, embedding_model, embedding, source_text)
        VALUES (:product_id, :embedding_model, CAST(:embedding AS vector), :source_text)
        ON CONFLICT (product_id)
        DO UPDATE SET
            embedding_model = EXCLUDED.embedding_model,
            embedding = EXCLUDED.embedding,
            source_text = EXCLUDED.source_text,
            updated_at = NOW()
        """
    )
    db.execute(
        query,
        {
            "product_id": product.id,
            "embedding_model": settings.embeddings_model,
            "embedding": vector_literal,
            "source_text": source_text,
        },
    )
    db.commit()


def semantic_search_products(
    db: Session,
    *,
    query_text: str,
    limit: int,
    is_active: bool | None = None,
) -> list[dict]:
    settings = get_settings()
    if not settings.embeddings_enabled:
        return []

    query_vector = generate_embedding(query_text)
    vector_literal = _vector_to_pg_literal(query_vector)
    sql = text(
        """
        SELECT
            p.id,
            p.name,
            p.description,
            p.sku,
            p.price,
            p.stock,
            p.is_active,
            p.created_at,
            p.updated_at,
            1 - (pe.embedding <=> CAST(:embedding AS vector)) AS score
        FROM product_embeddings pe
        INNER JOIN products p ON p.id = pe.product_id
        WHERE (:is_active IS NULL OR p.is_active = :is_active)
        ORDER BY pe.embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
        """
    )
    try:
        rows = db.execute(
            sql,
            {
                "embedding": vector_literal,
                "is_active": is_active,
                "limit": limit,
            },
        ).mappings()
    except Exception as exc:
        logger.exception("Semantic search failed due to vector store state.")
        raise EmbeddingsStoreNotReadyError(
            "Vector store is not ready. Run migrations and ensure pgvector is installed."
        ) from exc

    results: list[dict] = []
    for row in rows:
        results.append(
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "sku": row["sku"],
                "price": Decimal(row["price"]),
                "stock": row["stock"],
                "is_active": row["is_active"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "score": float(row["score"]),
            }
        )
    return results
