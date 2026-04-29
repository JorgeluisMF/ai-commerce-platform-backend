import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ReviewCreateRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def normalize_comment(self) -> "ReviewCreateRequest":
        self.comment = self.comment.strip()
        if not self.comment:
            raise ValueError("comment cannot be blank")
        return self


class ReviewUpdateRequest(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_fields(self) -> "ReviewUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided for update.")
        if self.comment is not None:
            self.comment = self.comment.strip()
            if not self.comment:
                raise ValueError("comment cannot be blank")
        return self


class ReviewResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    product_id: int
    rating: int
    comment: str
    created_at: datetime
