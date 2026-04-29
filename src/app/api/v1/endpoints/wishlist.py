from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps.auth import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.product import ProductResponse
from app.services import wishlist_service

router = APIRouter(prefix="/wishlist", tags=["wishlist"])


@router.get("", response_model=list[ProductResponse], summary="Get current user's wishlist")
def get_wishlist(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer)),
) -> list[ProductResponse]:
    return wishlist_service.get_wishlist_products(db, current_user.id)


@router.post(
    "/{product_id}",
    response_model=list[ProductResponse],
    status_code=status.HTTP_200_OK,
    summary="Add product to wishlist",
)
def add_to_wishlist(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer)),
) -> list[ProductResponse]:
    return wishlist_service.add_product_to_wishlist(
        db,
        user_id=current_user.id,
        product_id=product_id,
    )


@router.delete(
    "/{product_id}",
    response_model=list[ProductResponse],
    summary="Remove product from wishlist",
)
def remove_from_wishlist(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer)),
) -> list[ProductResponse]:
    return wishlist_service.remove_product_from_wishlist(
        db,
        user_id=current_user.id,
        product_id=product_id,
    )
