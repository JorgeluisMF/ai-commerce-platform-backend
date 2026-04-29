import uuid
from collections.abc import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.review import Review


def list_reviews_by_product_id(db: Session, product_id: int) -> list[Review]:
    return (
        db.query(Review)
        .filter(Review.product_id == product_id)
        .order_by(Review.created_at.desc())
        .all()
    )


def get_review_by_id(db: Session, review_id: uuid.UUID) -> Review | None:
    return db.query(Review).filter(Review.id == review_id).first()


def get_review_by_user_and_product(db: Session, *, user_id: uuid.UUID, product_id: int) -> Review | None:
    return (
        db.query(Review)
        .filter(Review.user_id == user_id, Review.product_id == product_id)
        .first()
    )


def get_product_review_stats(db: Session, product_ids: Iterable[int]) -> dict[int, tuple[float, int]]:
    ids = list({pid for pid in product_ids})
    if not ids:
        return {}
    rows = (
        db.query(
            Review.product_id,
            func.avg(Review.rating).label("average_rating"),
            func.count(Review.id).label("reviews_count"),
        )
        .filter(Review.product_id.in_(ids))
        .group_by(Review.product_id)
        .all()
    )
    result: dict[int, tuple[float, int]] = {}
    for row in rows:
        result[int(row.product_id)] = (float(row.average_rating or 0), int(row.reviews_count or 0))
    return result
