"""add product embeddings table

Revision ID: 20260427_02
Revises: 20260427_01
Create Date: 2026-04-27 10:55:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260427_02"
down_revision: str | None = "20260427_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS product_embeddings (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL UNIQUE REFERENCES products(id) ON DELETE CASCADE,
            embedding_model VARCHAR(120) NOT NULL,
            embedding VECTOR(1536) NOT NULL,
            source_text TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.create_index("ix_product_embeddings_product_id", "product_embeddings", ["product_id"], unique=True)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_product_embeddings_embedding_ivfflat "
        "ON product_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_product_embeddings_embedding_ivfflat")
    op.drop_index("ix_product_embeddings_product_id", table_name="product_embeddings")
    op.drop_table("product_embeddings")
