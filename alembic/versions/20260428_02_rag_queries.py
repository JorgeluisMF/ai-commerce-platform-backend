"""rag_queries table

Revision ID: 20260428_02
Revises: 20260428_01
Create Date: 2026-04-28 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260428_02"
down_revision: str | None = "20260428_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rag_queries",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("response_json", JSONB(), nullable=False),
        sa.Column("scores_json", JSONB(), nullable=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_rag_queries_created_at", "rag_queries", ["created_at"])
    op.create_index("ix_rag_queries_user_id", "rag_queries", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_rag_queries_user_id", table_name="rag_queries")
    op.drop_index("ix_rag_queries_created_at", table_name="rag_queries")
    op.drop_table("rag_queries")
