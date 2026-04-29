
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product import Product


def lock_products_by_ids_ordered(db: Session, product_ids: list[int]) -> dict[int, Product]:
    """Row-lock products in deterministic order (ascending id) to reduce deadlock risk."""
    if not product_ids:
        return {}
    sorted_ids = sorted(set(product_ids))
    stmt = (
        select(Product)
        .where(Product.id.in_(sorted_ids))
        .order_by(Product.id.asc())
        .with_for_update()
    )
    rows = db.scalars(stmt).all()
    return {p.id: p for p in rows}
