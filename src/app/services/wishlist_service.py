import uuid

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.http_exceptions import raise_api_error
from app.models.product import Product
from app.repositories import review_repository, wishlist_repository
from app.schemas.product import ProductResponse
from app.services.product_image_service import to_product_response


def _get_or_create_wishlist_id(db: Session, user_id: uuid.UUID) -> uuid.UUID:
    wishlist = wishlist_repository.get_wishlist_by_user_id(db, user_id)
    if wishlist is None:
        wishlist = wishlist_repository.create_wishlist(db, user_id)
        db.flush()
    return wishlist.id


def _to_products_with_stats(db: Session, product_ids: list[int]) -> list[ProductResponse]:
    if not product_ids:
        return []
    products = (
        db.query(Product)
        .options(selectinload(Product.images))
        .filter(Product.id.in_(product_ids))
        .all()
    )
    by_id = {p.id: p for p in products}
    stats = review_repository.get_product_review_stats(db, product_ids)
    result: list[ProductResponse] = []
    for product_id in product_ids:
        product = by_id.get(product_id)
        if product is None:
            continue
        average_rating, reviews_count = stats.get(product_id, (0.0, 0))
        result.append(
            to_product_response(
                product,
                average_rating=average_rating,
                reviews_count=reviews_count,
            )
        )
    return result


def get_wishlist_products(db: Session, user_id: uuid.UUID) -> list[ProductResponse]:
    wishlist = wishlist_repository.get_wishlist_by_user_id(db, user_id)
    if wishlist is None:
        return []
    items = wishlist_repository.list_wishlist_items(db, wishlist.id)
    product_ids = [item.product_id for item in items]
    return _to_products_with_stats(db, product_ids)


def add_product_to_wishlist(db: Session, *, user_id: uuid.UUID, product_id: int) -> list[ProductResponse]:
    product = db.get(Product, product_id)
    if product is None:
        raise_api_error(
            code="product_not_found",
            message=f"Product with id={product_id} was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    wishlist_id = _get_or_create_wishlist_id(db, user_id)
    existing = wishlist_repository.get_wishlist_item(
        db,
        wishlist_id=wishlist_id,
        product_id=product_id,
    )
    if existing is None:
        from app.models.wishlist import WishlistItem

        db.add(WishlistItem(wishlist_id=wishlist_id, product_id=product_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    return get_wishlist_products(db, user_id)


def remove_product_from_wishlist(
    db: Session,
    *,
    user_id: uuid.UUID,
    product_id: int,
) -> list[ProductResponse]:
    wishlist = wishlist_repository.get_wishlist_by_user_id(db, user_id)
    if wishlist is None:
        return []
    item = wishlist_repository.get_wishlist_item(
        db,
        wishlist_id=wishlist.id,
        product_id=product_id,
    )
    if item is not None:
        db.delete(item)
        db.commit()
    return get_wishlist_products(db, user_id)
