"""Widen product_images.storage_key for external image URLs.

Revision ID: 20260428_03
Revises: 20260428_02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260428_03"
down_revision: str | None = "20260428_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "product_images",
        "storage_key",
        existing_type=sa.String(length=512),
        type_=sa.String(length=2048),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "product_images",
        "storage_key",
        existing_type=sa.String(length=2048),
        type_=sa.String(length=512),
        existing_nullable=False,
    )
