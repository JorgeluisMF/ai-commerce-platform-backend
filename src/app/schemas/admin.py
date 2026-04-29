import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class OrdersByStatusResponse(BaseModel):
    pending: int = 0
    paid: int = 0
    shipped: int = 0
    cancelled: int = 0


class TopProductResponse(BaseModel):
    product_id: int
    name: str
    sales: int


class RecentOrderResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    status: str
    total_amount: Decimal
    currency: str
    created_at: datetime


class AdminDashboardResponse(BaseModel):
    total_users: int
    total_orders: int
    total_revenue: Decimal
    orders_by_status: OrdersByStatusResponse
    top_products: list[TopProductResponse]
    recent_orders: list[RecentOrderResponse]
