"""Order lifecycle: listing for owners, detail, and admin status transitions."""
import uuid
from decimal import Decimal

from fastapi import status
from sqlalchemy.orm import Session, joinedload

from app.core.http_exceptions import raise_api_error
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.schemas.order import (
    CheckoutOrderLineResponse,
    CheckoutResponse,
    OrderDetailResponse,
    OrderListItemResponse,
)

_ALLOWED_ADMIN_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.pending: frozenset({OrderStatus.paid, OrderStatus.cancelled}),
    OrderStatus.paid: frozenset({OrderStatus.shipped, OrderStatus.cancelled}),
    OrderStatus.shipped: frozenset(),
    OrderStatus.cancelled: frozenset(),
}


def list_orders_for_user(
    db: Session,
    *,
    user_id: uuid.UUID,
    page: int,
    page_size: int,
    status_filter: str | None,
) -> tuple[list[Order], int]:
    query = db.query(Order).filter(Order.user_id == user_id)
    if status_filter is not None:
        try:
            st = OrderStatus(status_filter)
        except ValueError:
            raise_api_error(
                code="invalid_order_status_filter",
                message="Invalid status filter value.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        query = query.filter(Order.status == st)
    total = query.count()
    rows = (
        query.order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def get_order_detail_for_user(db: Session, *, user_id: uuid.UUID, order_id: uuid.UUID) -> Order:
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.user_id == user_id)
        .options(joinedload(Order.items))
        .first()
    )
    if order is None:
        raise_api_error(
            code="order_not_found",
            message="Order was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return order


def product_name_for_line(db: Session, product_id: int) -> str:
    p = db.get(Product, product_id)
    return p.name if p else ""


def order_list_item(order: Order) -> OrderListItemResponse:
    return OrderListItemResponse(
        id=order.id,
        status=order.status.value,
        currency=order.currency,
        total_amount=order.total_amount,
        created_at=order.created_at,
    )


def order_to_detail_response(db: Session, order: Order) -> OrderDetailResponse:
    lines: list[CheckoutOrderLineResponse] = []
    for li in sorted(order.items, key=lambda x: (x.product_id, str(x.id))):
        lines.append(
            CheckoutOrderLineResponse(
                product_id=li.product_id,
                product_name=product_name_for_line(db, li.product_id),
                quantity=li.quantity,
                unit_price=li.unit_price,
                line_total=li.line_total,
            )
        )
    return OrderDetailResponse(
        id=order.id,
        status=order.status.value,
        currency=order.currency,
        total_amount=order.total_amount,
        created_at=order.created_at,
        items=lines,
    )


def order_to_checkout_response(db: Session, order: Order) -> CheckoutResponse:
    detail = order_to_detail_response(db, order)
    return CheckoutResponse(
        order_id=detail.id,
        status=detail.status,
        currency=detail.currency,
        total_amount=detail.total_amount,
        items=detail.items,
        created_at=detail.created_at,
    )


def admin_update_order_status(
    db: Session,
    *,
    order_id: uuid.UUID,
    new_status: OrderStatus,
) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise_api_error(
            code="order_not_found",
            message="Order was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    allowed = _ALLOWED_ADMIN_TRANSITIONS.get(order.status, frozenset())
    if new_status not in allowed:
        raise_api_error(
            code="invalid_status_transition",
            message=f"Cannot transition from {order.status.value} to {new_status.value}.",
            status_code=status.HTTP_409_CONFLICT,
            details={
                "current_status": order.status.value,
                "requested_status": new_status.value,
            },
        )
    order.status = new_status
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def get_order_by_id_any(db: Session, order_id: uuid.UUID) -> Order | None:
    return db.get(Order, order_id)


def mark_order_paid_simulated(db: Session, *, user_id: uuid.UUID, order_id: uuid.UUID) -> Order:
    """Mark a pending order paid (simulated payment gateway); idempotent if already paid."""
    order = (
        db.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()
    )
    if order is None:
        raise_api_error(
            code="order_not_found",
            message="Order was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if order.status == OrderStatus.paid:
        return order
    if order.status != OrderStatus.pending:
        raise_api_error(
            code="payment_not_allowed",
            message="Only pending orders can be paid with simulated payment.",
            status_code=status.HTTP_409_CONFLICT,
            details={"current_status": order.status.value},
        )
    order.status = OrderStatus.paid
    db.add(order)
    db.commit()
    db.refresh(order)
    return order
