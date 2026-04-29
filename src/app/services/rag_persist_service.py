"""Persist RAG Q&A for traceability; failures never propagate."""



from __future__ import annotations



import logging

import uuid

from typing import Any



from app.db.session import SessionLocal

from app.models.rag_query import RagQuery

from app.schemas.rag import RAGAnswerResponse



logger = logging.getLogger(__name__)





def persist_rag_query_record(

    *,

    question: str,

    response: RAGAnswerResponse,

    user_id: uuid.UUID | None = None,

) -> None:

    db = SessionLocal()

    try:

        scores: list[dict[str, Any]] = [

            {"product_id": c.product_id, "score": c.score} for c in response.citations

        ]

        payload = response.model_dump(mode="json")

        payload.pop("sources", None)

        row = RagQuery(

            question=question,

            response_json=payload,

            scores_json=scores,

            user_id=user_id,

        )

        db.add(row)

        db.commit()

    except Exception:

        logger.warning(

            "rag_query_persist_failed",

            exc_info=True,

            extra={"question_len": len(question)},

        )

        try:

            db.rollback()

        except Exception:

            pass

    finally:

        db.close()


