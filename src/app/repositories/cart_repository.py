import uuid

from sqlalchemy.orm import Session, joinedload

from app.models.cart import Cart, CartItem


def get_cart_by_user_id(db: Session, user_id: uuid.UUID) -> Cart | None:
    return (
        db.query(Cart)
        .filter(Cart.user_id == user_id)
        .options(joinedload(Cart.items))
        .first()
    )


def create_cart(db: Session, user_id: uuid.UUID) -> Cart:
    cart = Cart(user_id=user_id)
    db.add(cart)
    db.flush()
    return cart


def get_cart_item_for_user_cart(
    db: Session,
    *,
    cart_item_id: uuid.UUID,
    user_id: uuid.UUID,
) -> CartItem | None:
    return (
        db.query(CartItem)
        .join(Cart)
        .filter(Cart.user_id == user_id, CartItem.id == cart_item_id)
        .first()
    )


def count_distinct_products_in_cart(db: Session, cart_id: uuid.UUID) -> int:
    return db.query(CartItem).filter(CartItem.cart_id == cart_id).count()
