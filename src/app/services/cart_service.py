"""Cart use-cases: one cart per user, line merge, stock/limit checks, price snapshots."""
import uuid
from decimal import Decimal

from fastapi import status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.http_exceptions import raise_api_error
from app.models.cart import Cart, CartItem
from app.models.product import Product
from app.repositories import cart_repository
from app.schemas.cart import CartLineResponse, CartResponse


def _decimal_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _cart_to_response(db: Session, cart: Cart | None) -> CartResponse:
    if cart is None or not cart.items:
        return CartResponse(items=[], subtotal=Decimal("0.00"))

    lines: list[CartLineResponse] = []
    subtotal = Decimal("0.00")
    for item in cart.items:
        product = db.get(Product, item.product_id)
        name = product.name if product else ""
        line_subtotal = _decimal_money(item.unit_price_snapshot * item.quantity)
        subtotal += line_subtotal
        lines.append(
            CartLineResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=name,
                quantity=item.quantity,
                unit_price_snapshot=item.unit_price_snapshot,
                line_subtotal=line_subtotal,
            )
        )
    return CartResponse(items=lines, subtotal=_decimal_money(subtotal))


def get_cart(db: Session, user_id: uuid.UUID) -> CartResponse:
    """Return the current cart for the user, or an empty cart if none exists."""
    cart = cart_repository.get_cart_by_user_id(db, user_id)
    return _cart_to_response(db, cart)


def _get_or_create_cart(db: Session, user_id: uuid.UUID) -> Cart:
    cart = cart_repository.get_cart_by_user_id(db, user_id)
    if cart is None:
        cart = cart_repository.create_cart(db, user_id)
        db.refresh(cart)
    return cart


def add_cart_item(
    db: Session,
    *,
    user_id: uuid.UUID,
    product_id: int,
    quantity: int,
) -> CartResponse:
    """Add or merge a line; ``unit_price_snapshot`` is set from the product's current price."""
    settings = get_settings()
    cart = _get_or_create_cart(db, user_id)
    product = db.get(Product, product_id)
    if product is None:
        raise_api_error(
            code="product_not_found",
            message=f"Product with id={product_id} was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if not product.is_active:
        raise_api_error(
            code="product_unavailable",
            message="Product is not available for purchase.",
            status_code=status.HTTP_409_CONFLICT,
        )

    existing = (
        db.query(CartItem)
        .filter(CartItem.cart_id == cart.id, CartItem.product_id == product_id)
        .first()
    )

    merged_qty = quantity + (existing.quantity if existing else 0)

    if merged_qty > settings.cart_max_items_per_product:
        raise_api_error(
            code="max_quantity_per_product_exceeded",
            message=f"Quantity cannot exceed {settings.cart_max_items_per_product} per product.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if existing is None:
        current_lines = cart_repository.count_distinct_products_in_cart(db, cart.id)
        if current_lines >= settings.cart_max_lines:
            raise_api_error(
                code="max_cart_lines_exceeded",
                message=f"Cart cannot have more than {settings.cart_max_lines} distinct products.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    if merged_qty > product.stock:
        raise_api_error(
            code="insufficient_stock",
            message="Not enough stock for the requested quantity.",
            status_code=status.HTTP_409_CONFLICT,
        )

    snapshot = product.price
    if existing:
        existing.quantity = merged_qty
        existing.unit_price_snapshot = snapshot
        db.add(existing)
    else:
        db.add(
            CartItem(
                cart_id=cart.id,
                product_id=product_id,
                quantity=merged_qty,
                unit_price_snapshot=snapshot,
            )
        )
    db.commit()
    refreshed = cart_repository.get_cart_by_user_id(db, user_id)
    return _cart_to_response(db, refreshed)


def update_cart_item(
    db: Session,
    *,
    user_id: uuid.UUID,
    cart_item_id: uuid.UUID,
    quantity: int,
) -> CartResponse:
    """Update quantity for a line owned by the user's cart; refreshes price snapshot."""
    settings = get_settings()
    item = cart_repository.get_cart_item_for_user_cart(
        db,
        cart_item_id=cart_item_id,
        user_id=user_id,
    )
    if item is None:
        raise_api_error(
            code="cart_item_not_found",
            message="Cart line was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    product = db.get(Product, item.product_id)
    if product is None:
        raise_api_error(
            code="product_not_found",
            message=f"Product with id={item.product_id} was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if not product.is_active:
        raise_api_error(
            code="product_unavailable",
            message="Product is not available for purchase.",
            status_code=status.HTTP_409_CONFLICT,
        )

    if quantity > settings.cart_max_items_per_product:
        raise_api_error(
            code="max_quantity_per_product_exceeded",
            message=f"Quantity cannot exceed {settings.cart_max_items_per_product} per product.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if quantity > product.stock:
        raise_api_error(
            code="insufficient_stock",
            message="Not enough stock for the requested quantity.",
            status_code=status.HTTP_409_CONFLICT,
        )

    item.quantity = quantity
    item.unit_price_snapshot = product.price
    db.add(item)
    db.commit()
    refreshed = cart_repository.get_cart_by_user_id(db, user_id)
    return _cart_to_response(db, refreshed)


def remove_cart_item(db: Session, *, user_id: uuid.UUID, cart_item_id: uuid.UUID) -> CartResponse:
    """Delete a cart line; 404 if the line is not in the caller's cart."""
    item = cart_repository.get_cart_item_for_user_cart(
        db,
        cart_item_id=cart_item_id,
        user_id=user_id,
    )
    if item is None:
        raise_api_error(
            code="cart_item_not_found",
            message="Cart line was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    db.delete(item)
    db.commit()
    refreshed = cart_repository.get_cart_by_user_id(db, user_id)
    return _cart_to_response(db, refreshed)
