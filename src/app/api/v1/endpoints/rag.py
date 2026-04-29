import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.redis import get_redis_client
from app.db.session import get_db
from app.schemas.rag import RAGAnswerResponse, RAGQuestionRequest
from app.services.rag_persist_service import persist_rag_query_record
from app.services.rag_service import answer_with_rag
from app.services.rag_runtime_service import (
    append_rag_history,
    cache_rag_response,
    enforce_rag_rate_limit,
    get_cached_rag_response,
    get_rag_history,
)
from app.services.semantic_search_service import EmbeddingsStoreNotReadyError

router = APIRouter(prefix="/rag", tags=["rag"])
logger = logging.getLogger(__name__)


@router.post("/ask", response_model=RAGAnswerResponse, summary="Ask product RAG assistant")
def ask_rag_endpoint(
    payload: RAGQuestionRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> RAGAnswerResponse:
    redis_client = get_redis_client()
    client_ip = request.client.host if request.client and request.client.host else "unknown"
    allowed, remaining = enforce_rag_rate_limit(redis_client, client_id=client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded for RAG endpoint. Try again later. remaining={remaining}",
        )

    cached = get_cached_rag_response(
        redis_client,
        question=payload.question,
        top_k=payload.top_k,
        is_active=payload.is_active,
    )
    if cached is not None:
        logger.info("rag_cache_hit client_ip=%s", client_ip)
        append_rag_history(
            redis_client,
            client_id=client_ip,
            question=payload.question.strip(),
            answer=cached.answer,
        )
        background_tasks.add_task(
            persist_rag_query_record,
            question=payload.question.strip(),
            response=cached,
            user_id=None,
        )
        return cached

    try:
        history = get_rag_history(redis_client, client_id=client_ip)
        response = answer_with_rag(
            db=db,
            question=payload.question.strip(),
            top_k=payload.top_k,
            is_active=payload.is_active,
            chat_history=history,
        )
        cache_rag_response(
            redis_client,
            question=payload.question,
            top_k=payload.top_k,
            is_active=payload.is_active,
            response=response,
        )
        logger.info("rag_cache_miss client_ip=%s", client_ip)
        append_rag_history(
            redis_client,
            client_id=client_ip,
            question=payload.question.strip(),
            answer=response.answer,
        )
        background_tasks.add_task(
            persist_rag_query_record,
            question=payload.question.strip(),
            response=response,
            user_id=None,
        )
        return response
    except EmbeddingsStoreNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
