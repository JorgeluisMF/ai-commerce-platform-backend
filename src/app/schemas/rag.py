from pydantic import BaseModel, Field, computed_field


class RAGQuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    is_active: bool | None = True


class RAGCitation(BaseModel):
    product_id: int
    sku: str
    name: str
    score: float


class RAGAnswerResponse(BaseModel):
    question: str
    answer: str
    citations: list[RAGCitation]
    used_context_chars: int
    total_candidates: int
    used_candidates: int
    low_confidence: bool

    @computed_field
    @property
    def sources(self) -> list[RAGCitation]:
        """Alias of ``citations`` for clients expecting a ``sources`` field."""
        return self.citations
