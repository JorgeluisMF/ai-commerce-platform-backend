import uuid

from sqlalchemy.orm import Session

from app.models.wishlist import Wishlist, WishlistItem


def get_wishlist_by_user_id(db: Session, user_id: uuid.UUID) -> Wishlist | None:
    return db.query(Wishlist).filter(Wishlist.user_id == user_id).first()


def create_wishlist(db: Session, user_id: uuid.UUID) -> Wishlist:
    wishlist = Wishlist(user_id=user_id)
    db.add(wishlist)
    db.flush()
    return wishlist


def get_wishlist_item(
    db: Session,
    *,
    wishlist_id: uuid.UUID,
    product_id: int,
) -> WishlistItem | None:
    return (
        db.query(WishlistItem)
        .filter(WishlistItem.wishlist_id == wishlist_id, WishlistItem.product_id == product_id)
        .first()
    )


def list_wishlist_items(db: Session, wishlist_id: uuid.UUID) -> list[WishlistItem]:
    return (
        db.query(WishlistItem)
        .filter(WishlistItem.wishlist_id == wishlist_id)
        .order_by(WishlistItem.created_at.desc())
        .all()
    )
