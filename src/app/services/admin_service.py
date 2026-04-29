from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product
from app.models.user import User
from app.schemas.admin import (
    AdminDashboardResponse,
    OrdersByStatusResponse,
    RecentOrderResponse,
    TopProductResponse,
)


def get_dashboard_metrics(db: Session) -> AdminDashboardResponse:
    total_users = int(db.query(func.count(User.id)).scalar() or 0)
    total_orders = int(db.query(func.count(Order.id)).scalar() or 0)
    total_revenue = db.query(func.coalesce(func.sum(Order.total_amount), 0)).filter(Order.status == OrderStatus.paid).scalar()
    total_revenue = Decimal(total_revenue or 0)

    status_rows = (
        db.query(Order.status, func.count(Order.id))
        .group_by(Order.status)
        .all()
    )
    status_counts = {str(status.value): int(count) for status, count in status_rows}
    orders_by_status = OrdersByStatusResponse(
        pending=status_counts.get("pending", 0),
        paid=status_counts.get("paid", 0),
        shipped=status_counts.get("shipped", 0),
        cancelled=status_counts.get("cancelled", 0),
    )

    top_rows = (
        db.query(
            OrderItem.product_id,
            Product.name,
            func.sum(OrderItem.quantity).label("sales"),
        )
        .join(Product, Product.id == OrderItem.product_id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.status.in_([OrderStatus.paid, OrderStatus.shipped]))
        .group_by(OrderItem.product_id, Product.name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(5)
        .all()
    )
    top_products = [
        TopProductResponse(
            product_id=int(row.product_id),
            name=row.name,
            sales=int(row.sales or 0),
        )
        for row in top_rows
    ]

    recent_rows = db.query(Order).order_by(Order.created_at.desc()).limit(10).all()
    recent_orders = [
        RecentOrderResponse(
            id=row.id,
            user_id=row.user_id,
            status=row.status.value,
            total_amount=row.total_amount,
            currency=row.currency,
            created_at=row.created_at,
        )
        for row in recent_rows
    ]

    return AdminDashboardResponse(
        total_users=total_users,
        total_orders=total_orders,
        total_revenue=total_revenue,
        orders_by_status=orders_by_status,
        top_products=top_products,
        recent_orders=recent_orders,
    )
