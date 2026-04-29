import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.pagination import Paged


class CheckoutOrderLineResponse(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class OrderListItemResponse(BaseModel):
    id: uuid.UUID
    status: str
    currency: str
    total_amount: Decimal
    created_at: datetime


class OrderStatusPatchRequest(BaseModel):
    status: str = Field(
        description="Target order status (admin only, must be a valid transition).",
    )


class OrderDetailResponse(BaseModel):
    id: uuid.UUID
    status: str
    currency: str
    total_amount: Decimal
    created_at: datetime
    items: list[CheckoutOrderLineResponse]


class CheckoutResponse(BaseModel):
    order_id: uuid.UUID
    status: str
    currency: str
    total_amount: Decimal
    items: list[CheckoutOrderLineResponse]
    created_at: datetime


class UserOrderListResponse(Paged[OrderListItemResponse]):
    pass
