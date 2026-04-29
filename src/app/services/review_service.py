import uuid

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.http_exceptions import raise_api_error
from app.models.product import Product
from app.models.review import Review
from app.repositories import review_repository
from app.schemas.review import ReviewCreateRequest, ReviewResponse, ReviewUpdateRequest


def _to_review_response(review: Review) -> ReviewResponse:
    return ReviewResponse(
        id=review.id,
        user_id=review.user_id,
        product_id=review.product_id,
        rating=review.rating,
        comment=review.comment,
        created_at=review.created_at,
    )


def list_product_reviews(db: Session, product_id: int) -> list[ReviewResponse]:
    product = db.get(Product, product_id)
    if product is None:
        raise_api_error(
            code="product_not_found",
            message=f"Product with id={product_id} was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    rows = review_repository.list_reviews_by_product_id(db, product_id)
    return [_to_review_response(row) for row in rows]


def create_review_for_product(
    db: Session,
    *,
    user_id: uuid.UUID,
    product_id: int,
    payload: ReviewCreateRequest,
) -> ReviewResponse:
    product = db.get(Product, product_id)
    if product is None:
        raise_api_error(
            code="product_not_found",
            message=f"Product with id={product_id} was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    review = Review(
        user_id=user_id,
        product_id=product_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(review)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise_api_error(
            code="review_already_exists",
            message="You already reviewed this product.",
            status_code=status.HTTP_409_CONFLICT,
        )
    db.refresh(review)
    return _to_review_response(review)


def update_review(
    db: Session,
    *,
    review_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: ReviewUpdateRequest,
) -> ReviewResponse:
    review = review_repository.get_review_by_id(db, review_id)
    if review is None:
        raise_api_error(
            code="review_not_found",
            message="Review was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if review.user_id != user_id:
        raise_api_error(
            code="forbidden",
            message="You can only edit your own review.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(review, field_name, value)
    db.add(review)
    db.commit()
    db.refresh(review)
    return _to_review_response(review)


def delete_review(db: Session, *, review_id: uuid.UUID, user_id: uuid.UUID) -> None:
    review = review_repository.get_review_by_id(db, review_id)
    if review is None:
        raise_api_error(
            code="review_not_found",
            message="Review was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if review.user_id != user_id:
        raise_api_error(
            code="forbidden",
            message="You can only delete your own review.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    db.delete(review)
    db.commit()
