"""RQ job entrypoints (import-safe; workers load this module)."""

from __future__ import annotations


def index_product_embedding_job(product_id: int) -> None:
    from sqlalchemy.orm import Session

    from app.db.session import SessionLocal
    from app.models.product import Product
    from app.services.semantic_search_service import index_product_embedding

    db: Session = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if product is None:
            return
        index_product_embedding(db, product)
        db.commit()
    finally:
        db.close()


def noop_email(subject: str, body: str) -> None:
    """Placeholder job for the emails queue (extend with real SMTP/sendgrid dispatch)."""
    import logging

    logging.getLogger(__name__).info("noop_email subject=%s", subject[:120])


def post_checkout_stub(order_id: str) -> None:
    import logging

    logging.getLogger(__name__).info("post_checkout_stub order_id=%s", order_id)
