import logging
import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from fastapi import status
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.http_exceptions import raise_api_error
from app.models.order import Order, OrderItem, OrderStatus
from app.repositories import cart_repository, order_repository
from app.schemas.order import CheckoutOrderLineResponse, CheckoutResponse
from app.services.idempotency_service import (
    compute_key,
    get_cached_response,
    set_cached_response,
)
if TYPE_CHECKING:
    from redis import Redis

logger = logging.getLogger(__name__)


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def checkout(
    db: Session,
    user_id: uuid.UUID,
    *,
    idempotency_key: str | None = None,
    redis_client: "Redis | None" = None,
) -> CheckoutResponse:
    """
    Create an order from the user's cart in one DB transaction.

    Locks product rows (``FOR UPDATE``), validates stock and optional price parity
    with cart snapshots, persists ``orders`` / ``order_items``, decrements stock,
    and removes cart lines. Rolls back on any failure before commit.

    When ``Idempotency-Key`` is provided with a Redis client, an existing mapping
    returns the same checkout response without duplicating the order.
    """
    settings = get_settings()
    rkey: str | None = None
    if idempotency_key and redis_client:
        normalized = idempotency_key.strip()
        if normalized:
            try:
                rkey = compute_key(user_id, normalized, "checkout")
            except ValueError:
                rkey = None
            if rkey:
                try:
                    cached = get_cached_response(redis_client, rkey)
                    if cached:
                        _code, body = cached
                        return CheckoutResponse.model_validate(body)
                except RedisError:
                    raise_api_error(
                        code="redis_unavailable",
                        message="Checkout idempotency requires Redis; try again shortly.",
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )

    currency = settings.order_currency.strip().upper()
    if len(currency) != 3:
        currency = "USD"

    cart = cart_repository.get_cart_by_user_id(db, user_id)
    if not cart or not cart.items:
        raise_api_error(
            code="empty_cart",
            message="Cart is empty.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    lines = list(cart.items)
    by_product = {item.product_id: item for item in lines}
    product_ids = list(by_product.keys())

    locked = order_repository.lock_products_by_ids_ordered(db, product_ids)
    if len(locked) != len(product_ids):
        raise_api_error(
            code="product_not_found",
            message="One or more products are no longer available.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if settings.checkout_reject_on_price_mismatch:
        mismatched: list[int] = []
        for pid in sorted(by_product.keys()):
            line = by_product[pid]
            product = locked[pid]
            if _quantize_money(line.unit_price_snapshot) != _quantize_money(product.price):
                mismatched.append(pid)
        if mismatched:
            raise_api_error(
                code="price_changed",
                message="One or more product prices changed. Refresh your cart and try again.",
                status_code=status.HTTP_409_CONFLICT,
                details={"product_ids": mismatched},
            )

    order_lines: list[tuple[int, int, Decimal, Decimal, str]] = []
    total = Decimal("0.00")

    for pid in sorted(by_product.keys()):
        product = locked[pid]
        line = by_product[pid]
        qty = line.quantity
        if not product.is_active:
            raise_api_error(
                code="product_unavailable",
                message="One or more products are not available for purchase.",
                status_code=status.HTTP_409_CONFLICT,
            )
        if product.stock < qty:
            raise_api_error(
                code="insufficient_stock",
                message="Not enough stock to complete checkout.",
                status_code=status.HTTP_409_CONFLICT,
            )
        unit = product.price
        line_total = (unit * qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total += line_total
        order_lines.append((pid, qty, unit, line_total, product.name))

    total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    order_id: uuid.UUID
    created_at_ts: datetime
    try:
        order = Order(
            user_id=user_id,
            status=OrderStatus.pending,
            currency=currency,
            total_amount=total,
        )
        db.add(order)
        db.flush()
        db.refresh(order)

        for pid, qty, unit, line_total, _name in order_lines:
            db.add(
                OrderItem(
                    order_id=order.id,
                    product_id=pid,
                    quantity=qty,
                    unit_price=unit,
                    line_total=line_total,
                )
            )
            locked[pid].stock -= qty

        for item in lines:
            db.delete(item)

        order_id = order.id
        created_at_ts = order.created_at

        db.commit()
    except Exception:
        db.rollback()
        raise

    response = CheckoutResponse(
        order_id=order_id,
        status=OrderStatus.pending.value,
        currency=currency,
        total_amount=total,
        items=[
            CheckoutOrderLineResponse(
                product_id=pid,
                product_name=name,
                quantity=qty,
                unit_price=unit,
                line_total=lt,
            )
            for pid, qty, unit, lt, name in order_lines
        ],
        created_at=created_at_ts,
    )

    if rkey and redis_client:
        set_cached_response(
            redis_client,
            rkey,
            status_code=status.HTTP_201_CREATED,
            body=response.model_dump(mode="json"),
            ttl_sec=settings.idempotency_ttl_sec,
        )

    logger.info(
        "checkout_completed",
        extra={
            "order_id": str(order_id),
            "user_id": str(user_id),
            "currency": currency,
            "total_amount": str(total),
            "line_count": len(order_lines),
        },
    )

    return response
