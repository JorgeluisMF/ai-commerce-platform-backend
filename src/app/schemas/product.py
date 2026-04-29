from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.pagination import Paged


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120, description="Product display name")
    description: str | None = Field(default=None, max_length=500)
    sku: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Stock keeping unit, unique and URL-safe",
    )
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    stock: int = Field(ge=0, le=1_000_000)
    is_active: bool = True
    images: list[str] = Field(
        default_factory=list,
        description="HTTPS image URLs attached at creation (order preserved; first is primary).",
        max_length=40,
    )

    @field_validator("images")
    @classmethod
    def validate_image_urls(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in value:
            u = raw.strip()
            if not u:
                continue
            if not (u.startswith("http://") or u.startswith("https://")):
                raise ValueError("each image URL must start with http:// or https://")
            if len(u) > 2048:
                raise ValueError("image URL exceeds maximum length")
            cleaned.append(u)
        return cleaned

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be blank")
        return normalized

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        return value.strip().upper()


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    sku: str
    price: Decimal
    stock: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    images: list[str] = Field(default_factory=list)
    average_rating: float = Field(default=0.0, ge=0, le=5)
    reviews_count: int = Field(default=0, ge=0)


class ProductListResponse(Paged[ProductResponse]):
    """Paginated product listing (see ``page`` / ``page_size`` query params)."""


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    sku: str | None = Field(default=None, min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    stock: int | None = Field(default=None, ge=0, le=1_000_000)
    is_active: bool | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ProductUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided for update.")
        return self

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be blank")
        return normalized

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return value.strip().upper()


class ProductSemanticResult(BaseModel):
    product: ProductResponse
    score: float


class SemanticSearchPaginationMeta(BaseModel):
    """
    Pagination summary for semantic search.

    Semantic search returns a single page only; ``total`` is the count of hits in this response.
    """

    total: int
    page: int = 1
    page_size: int
    pages: int


class ProductSemanticSearchResponse(BaseModel):
    query: str
    limit: int
    items: list[ProductSemanticResult]
    meta: SemanticSearchPaginationMeta
