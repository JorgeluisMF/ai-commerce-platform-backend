import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps.auth import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.review import ReviewCreateRequest, ReviewResponse, ReviewUpdateRequest
from app.services import review_service

router = APIRouter(tags=["reviews"])


@router.get(
    "/products/{product_id}/reviews",
    response_model=list[ReviewResponse],
    summary="List product reviews",
)
def list_product_reviews(
    product_id: int,
    db: Session = Depends(get_db),
) -> list[ReviewResponse]:
    return review_service.list_product_reviews(db, product_id)


@router.post(
    "/products/{product_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create product review",
)
def create_product_review(
    product_id: int,
    payload: ReviewCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer)),
) -> ReviewResponse:
    return review_service.create_review_for_product(
        db,
        user_id=current_user.id,
        product_id=product_id,
        payload=payload,
    )


@router.patch(
    "/reviews/{review_id}",
    response_model=ReviewResponse,
    summary="Update own review",
)
def update_review(
    review_id: uuid.UUID,
    payload: ReviewUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer)),
) -> ReviewResponse:
    return review_service.update_review(
        db,
        review_id=review_id,
        user_id=current_user.id,
        payload=payload,
    )


@router.delete(
    "/reviews/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete own review",
)
def delete_review(
    review_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer)),
) -> None:
    review_service.delete_review(db, review_id=review_id, user_id=current_user.id)
