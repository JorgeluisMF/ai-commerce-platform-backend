from typing import Generic, TypeVar

from pydantic import BaseModel, computed_field


T = TypeVar("T")


class Paged(BaseModel, Generic[T]):
    """Standard paginated envelope for list endpoints."""

    items: list[T]
    total: int
    page: int
    page_size: int

    @computed_field
    @property
    def pages(self) -> int:
        if self.page_size <= 0:
            return 0
        if self.total == 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size
