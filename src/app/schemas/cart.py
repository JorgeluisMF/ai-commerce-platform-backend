import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CartItemAddRequest(BaseModel):
    product_id: int = Field(ge=1)
    quantity: int = Field(ge=1, le=1_000_000)


class CartItemUpdateRequest(BaseModel):
    quantity: int = Field(ge=1, le=1_000_000)


class CartLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: int
    product_name: str
    quantity: int
    unit_price_snapshot: Decimal
    line_subtotal: Decimal


class CartResponse(BaseModel):
    items: list[CartLineResponse]
    subtotal: Decimal

