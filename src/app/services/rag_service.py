from __future__ import annotations

import logging
import re
from time import perf_counter

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_groq import ChatGroq
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.schemas.rag import RAGAnswerResponse, RAGCitation
from app.core.config import get_settings
from app.models.product import Product
from app.services.semantic_search_service import semantic_search_products

logger = logging.getLogger(__name__)

_MIN_TOKEN_LEN = 2
_STOPWORDS = {
    "the",
    "a",
    "an",
    "of",
    "for",
    "with",
    "in",
    "how",
    "want",
    "need",
    "information",
    "product",
    "products",
    "here",
    "there",
    "have",
}
_SYNONYMS = {
    "watch": "smartwatch",
    "clock": "smartwatch",
    "phone": "smartphone",
    "mobile": "smartphone",
    "cell": "smartphone",
}
_GREETING_PATTERNS = {
    "hi",
    "good morning",
    "good afternoon",
    "good evening",
    "hey",
    "hello",
}
_CATEGORY_ALIASES = {
    "gaming": {"gaming", "gamer"},
    "smartwatch": {"smartwatch", "watch", "clock"},
    "smartphone": {"smartphone", "phone", "mobile", "cell"},
}
_CHECKOUT_HELP_CONTEXT = (
    "Customer flow in this e-commerce app:\n"
    "- View the catalog at /products and open the product detail page.\n"
    "- To buy: sign in, add to cart, and then go to /checkout.\n"
    "- If asked for budget recommendations, prioritize lower price and confirm stock."
)


def _normalize_groq_sdk_base_url(url: str) -> str:
    """Official ``groq`` client expects host root; it appends ``/openai/v1/...`` itself.

    If ``GROQ_BASE_URL`` is set to the OpenAI-compatible path (``.../openai/v1``),
    passing it verbatim duplicates the path (404 on ``/openai/v1/openai/v1/...``).
    """
    u = url.strip().rstrip("/")
    if u.endswith("/openai/v1"):
        u = u[: -len("/openai/v1")]
    return u or "https://api.groq.com"


class RAGChainLogCallback(BaseCallbackHandler):
    def on_llm_start(self, serialized, prompts, **kwargs):  # type: ignore[override]
        logger.info("rag_llm_start provider=%s prompts=%s", serialized.get("name"), len(prompts))

    def on_llm_end(self, response, **kwargs):  # type: ignore[override]
        logger.info("rag_llm_end generations=%s", len(response.generations))

    def on_llm_error(self, error, **kwargs):  # type: ignore[override]
        logger.exception("rag_llm_error error=%s", error)


def _low_confidence_fallback() -> str:
    return (
        "I do not have enough catalog evidence to answer confidently. "
        "Try a more specific question or add more detailed product descriptions."
    )


def _local_rag_model(payload: dict) -> str:
    context = payload.get("context", "").strip()
    question = payload.get("question", "").strip()
    if not context:
        return _low_confidence_fallback()
    return (
        "Catalog-context assisted answer.\n"
        f"Question: {question}\n"
        "Tip: compare price, stock, and description before recommending."
    )


def _prompt_for_intent(question: str) -> ChatPromptTemplate:
    normalized = question.lower()
    if any(keyword in normalized for keyword in ["compara", "versus", "vs"]):
        system = (
            "You are an e-commerce assistant specialized in product comparison. "
            "Compare objectively using only the context."
        )
    elif any(keyword in normalized for keyword in ["stock", "available", "inventory"]):
        system = (
            "You are an e-commerce assistant focused on availability. "
            "Prioritize stock and active status using only the context."
        )
    else:
        system = (
            "You are an e-commerce assistant. Answer only based on the given context. "
            "If context is missing, state it clearly."
        )

    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                system
                + " "
                + (
                    "If they ask how to get/buy a product, explain concrete steps "
                    "on this platform. "
                    "If they ask for a category (for example gaming, smartphone, or smartwatch), "
                    "list only products that actually appear in context. "
                    "If the question uses references like 'that one', 'both', or 'the first one', use chat history. "
                    "Do not expose internal product IDs in the response. "
                    "Never invent products or prices."
                ),
            ),
            (
                "human",
                "Recent history:\n{chat_history}\n\n"
                "Context:\n{context}\n\nQuestion:\n{question}\n\n"
                "Respond in English, clearly and briefly.",
            ),
        ]
    )


def _build_langchain_chain(question: str):
    settings = get_settings()
    prompt = _prompt_for_intent(question)
    parser = StrOutputParser()

    provider = settings.llm_provider.lower().strip()
    if provider == "groq":
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is required when LLM_PROVIDER=groq.")
        model = ChatGroq(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            groq_api_key=settings.groq_api_key,
            base_url=_normalize_groq_sdk_base_url(settings.groq_base_url),
        )
        return prompt | model | parser

    if provider == "local":
        # Lightweight chain without external API; RunnableLambda expects a payload dict.
        return RunnableLambda(_local_rag_model)

    msg = f"LLM_PROVIDER must be one of: local, groq (received value: {provider!r})."
    raise RuntimeError(msg)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.4, min=0.4, max=2.0),
    retry=retry_if_exception_type(Exception),
)
def _invoke_chain_with_retry(chain, *, question: str, context: str, chat_history: str) -> str:
    callbacks = [RAGChainLogCallback()]
    return chain.invoke(
        {"question": question, "context": context, "chat_history": chat_history},
        config={"callbacks": callbacks, "tags": ["rag", "catalog_assistant"]},
    )


def _build_context(rows: list[dict], *, max_chars: int) -> tuple[str, int]:
    context_blocks: list[str] = []
    used_count = 0
    current_length = 0
    for row in rows:
        block = (
            f"- sku: {row['sku']}\n"
            f"  name: {row['name']}\n"
            f"  description: {row['description'] or ''}\n"
            f"  price: {row['price']}\n"
            f"  stock: {row['stock']}\n"
            f"  score: {row['score']:.4f}"
        )
        projected = current_length + len(block) + (1 if context_blocks else 0)
        if projected > max_chars:
            break
        context_blocks.append(block)
        current_length = projected
        used_count += 1
    helper_projected = current_length + len(_CHECKOUT_HELP_CONTEXT) + (1 if context_blocks else 0)
    if helper_projected <= max_chars:
        context_blocks.append(_CHECKOUT_HELP_CONTEXT)
    return "\n".join(context_blocks), used_count


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def _is_small_talk(question: str) -> bool:
    q = _normalize_text(question)
    return q in _GREETING_PATTERNS


def _small_talk_response() -> str:
    return "Hi, how can I help you?"


def _is_capability_question(question: str) -> bool:
    q = _normalize_text(question)
    return q in {
        "how can you help me",
        "what can you help me with",
        "what can you do",
        "what do you help with",
    }


def _capability_response() -> str:
    return "I can help with products, prices, stock, recommendations, and how to buy in the store."


def _is_system_help_question(question: str) -> bool:
    q = _normalize_text(question)
    triggers = [
        "how does this system work",
        "how does this platform work",
        "how does the system work",
        "how does it work",
        "explain the system",
        "explain the platform",
    ]
    return any(t in q for t in triggers)


def _system_help_response() -> str:
    return (
        "This platform lets you view products, check price and stock, receive recommendations, "
        "add to cart, and complete checkout."
    )


def _is_catalog_overview_question(question: str) -> bool:
    q = _normalize_text(question)
    triggers = [
        "available products",
        "what products are available",
        "what is available",
        "catalog",
        "available inventory",
    ]
    return any(t in q for t in triggers)


def _available_products(*, db, is_active: bool | None, limit: int) -> list[Product]:
    query = db.query(Product)
    if is_active is not None:
        query = query.filter(Product.is_active == is_active)
    return query.order_by(Product.name.asc()).limit(limit).all()


def _catalog_overview_response(products: list[Product]) -> str:
    if not products:
        return "I could not find available products at this moment."
    lines = ["Here are some available products:"]
    for product in products:
        lines.append(f"- {product.name} ({product.sku})")
    lines.append("If you want, I can share the price and details of the one you choose.")
    return "\n".join(lines)


def _detected_categories(question: str) -> set[str]:
    q = _normalize_text(question)
    q_tokens = set(q.split(" "))
    detected: set[str] = set()
    for canonical, aliases in _CATEGORY_ALIASES.items():
        if aliases & q_tokens:
            detected.add(canonical)
    return detected


def _question_tokens(question: str) -> set[str]:
    normalized = _normalize_text(question)
    raw_tokens = [token for token in normalized.split(" ") if len(token) >= _MIN_TOKEN_LEN]
    expanded: list[str] = []
    for token in raw_tokens:
        expanded.append(token)
        synonym = _SYNONYMS.get(token)
        if synonym:
            expanded.append(synonym)
    return {token for token in expanded if token not in _STOPWORDS}


def _exact_match_products(*, db, question: str, is_active: bool | None, limit: int) -> list[dict]:
    q_norm = _normalize_text(question)
    q_tokens = _question_tokens(question)
    if not q_norm:
        return []

    query = db.query(Product)
    if is_active is not None:
        query = query.filter(Product.is_active == is_active)
    products = query.all()
    categories = _detected_categories(question)

    candidates: list[tuple[float, Product]] = []
    for product in products:
        name_norm = _normalize_text(product.name)
        sku_norm = _normalize_text(product.sku)
        description_norm = _normalize_text(product.description or "")

        score = 0.0
        if q_norm == name_norm:
            score = 1.0
        elif q_norm == sku_norm or sku_norm.replace(" ", "") in q_norm.replace(" ", ""):
            score = 0.99
        elif q_norm in name_norm:
            score = 0.97
        else:
            name_tokens = {token for token in name_norm.split(" ") if len(token) >= _MIN_TOKEN_LEN}
            if q_tokens and name_tokens:
                intersection = q_tokens & name_tokens
                overlap = len(intersection) / max(len(name_tokens), 1)
                if overlap >= 0.4 or len(intersection) >= 1:
                    score = 0.9 + (0.05 * overlap)
        if categories:
            for category in categories:
                if category in name_norm or category in description_norm:
                    score = max(score, 0.96)

        if score > 0:
            candidates.append((score, product))

    candidates.sort(key=lambda item: (item[0], item[1].id), reverse=True)
    rows: list[dict] = []
    for score, product in candidates[:limit]:
        rows.append(
            {
                "id": product.id,
                "name": product.name,
                "description": product.description,
                "sku": product.sku,
                "price": product.price,
                "stock": product.stock,
                "is_active": product.is_active,
                "created_at": product.created_at,
                "updated_at": product.updated_at,
                "score": float(score),
            }
        )
    return rows


def _merge_retrieval_rows(*, exact_rows: list[dict], semantic_rows: list[dict], limit: int) -> list[dict]:
    merged_by_id: dict[int, dict] = {}
    for row in exact_rows + semantic_rows:
        existing = merged_by_id.get(row["id"])
        if existing is None or row["score"] > existing["score"]:
            merged_by_id[row["id"]] = row
    merged = list(merged_by_id.values())
    merged.sort(key=lambda row: row["score"], reverse=True)
    return merged[:limit]


def _format_chat_history(history: list[dict]) -> str:
    if not history:
        return "No history."
    lines: list[str] = []
    for turn in history[-4:]:
        q = str(turn.get("question", "")).strip()
        a = str(turn.get("answer", "")).strip()
        if not q and not a:
            continue
        lines.append(f"- User: {q}")
        lines.append(f"- Assistant: {a}")
    return "\n".join(lines) if lines else "No history."


def _apply_relevance_floor(rows: list[dict], *, min_score: float) -> list[dict]:
    floor = max(min_score, 0.12)
    kept = [row for row in rows if row["score"] >= 0.9 or row["score"] >= floor]
    return kept


def _structured_category_answer(question: str, rows: list[dict]) -> str | None:
    categories = _detected_categories(question)
    if not categories:
        return None
    if not rows:
        return "I could not find products from that category in the current catalog."
    lines = ["Here are the related products I found:"]
    for row in rows[:5]:
        lines.append(
            f"- {row['name']} ({row['sku']}): ${row['price']} | stock {row['stock']}"
        )
    return "\n".join(lines)


def _structured_followup_answer(question: str) -> str | None:
    q = _normalize_text(question)
    if "how" in q and ("buy" in q or "get" in q) and ("both" in q or "the two" in q):
        return (
            "To buy both products: 1) sign in, 2) open each mentioned product detail page, "
            "3) add both to cart, and 4) complete checkout at /checkout."
        )
    return None


def _is_cheapest_request(question: str) -> bool:
    q = _normalize_text(question)
    triggers = ["cheapest", "cheap", "budget", "lowest price", "most affordable"]
    return any(token in q for token in triggers)


def _cheapest_products(*, db, is_active: bool | None, limit: int) -> list[Product]:
    query = db.query(Product)
    if is_active is not None:
        query = query.filter(Product.is_active == is_active)
    return query.order_by(Product.price.asc(), Product.id.asc()).limit(limit).all()


def _structured_cheapest_answer(products: list[Product]) -> str:
    if not products:
        return "I could not find available products at this moment."
    lines = ["Here are the cheapest products I found:"]
    for product in products:
        lines.append(f"- {product.name}: ${product.price} | stock {product.stock}")
    return "\n".join(lines)


def _single_product_structured_answer(rows: list[dict]) -> str | None:
    if not rows:
        return None
    top = rows[0]
    if top["score"] < 0.9:
        return None
    return (
        f"{top['name']} ({top['sku']}): ${top['price']} | stock {top['stock']}. "
        f"Description: {top['description'] or 'No description'}."
    )


def answer_with_rag(
    *,
    db,
    question: str,
    top_k: int,
    is_active: bool | None,
    chat_history: list[dict] | None = None,
) -> RAGAnswerResponse:
    settings = get_settings()
    started_at = perf_counter()
    if _is_small_talk(question):
        answer = _small_talk_response()
        return RAGAnswerResponse(
            question=question,
            answer=answer,
            citations=[],
            used_context_chars=0,
            total_candidates=0,
            used_candidates=0,
            low_confidence=False,
        )
    if _is_capability_question(question):
        return RAGAnswerResponse(
            question=question,
            answer=_capability_response(),
            citations=[],
            used_context_chars=0,
            total_candidates=0,
            used_candidates=0,
            low_confidence=False,
        )
    if _is_system_help_question(question):
        return RAGAnswerResponse(
            question=question,
            answer=_system_help_response(),
            citations=[],
            used_context_chars=0,
            total_candidates=0,
            used_candidates=0,
            low_confidence=False,
        )
    if _is_catalog_overview_question(question):
        available = _available_products(db=db, is_active=is_active, limit=10)
        return RAGAnswerResponse(
            question=question,
            answer=_catalog_overview_response(available),
            citations=[],
            used_context_chars=0,
            total_candidates=len(available),
            used_candidates=len(available),
            low_confidence=False,
        )
    if _is_cheapest_request(question):
        cheapest = _cheapest_products(db=db, is_active=is_active, limit=5)
        return RAGAnswerResponse(
            question=question,
            answer=_structured_cheapest_answer(cheapest),
            citations=[],
            used_context_chars=0,
            total_candidates=len(cheapest),
            used_candidates=len(cheapest),
            low_confidence=False,
        )

    semantic_rows = semantic_search_products(db=db, query_text=question, limit=top_k, is_active=is_active)
    exact_rows = _exact_match_products(db=db, question=question, is_active=is_active, limit=top_k)
    rows = _merge_retrieval_rows(exact_rows=exact_rows, semantic_rows=semantic_rows, limit=max(top_k, 10))

    filtered_rows = _apply_relevance_floor(rows, min_score=settings.rag_min_score)
    context, used_candidates = _build_context(filtered_rows, max_chars=settings.rag_max_context_chars)
    low_confidence = len(filtered_rows) == 0
    structured = (
        _structured_followup_answer(question)
        or _structured_category_answer(question, filtered_rows)
        or _single_product_structured_answer(filtered_rows)
    )
    if structured:
        answer = structured
        low_confidence = False
    elif low_confidence:
        answer = _low_confidence_fallback()
    else:
        chain = _build_langchain_chain(question)
        answer = _invoke_chain_with_retry(
            chain,
            question=question,
            context=context,
            chat_history=_format_chat_history(chat_history or []),
        )

    elapsed_ms = round((perf_counter() - started_at) * 1000, 2)
    logger.info(
        "rag_answer_generated question_len=%s top_k=%s total_candidates=%s used_candidates=%s low_confidence=%s context_chars=%s elapsed_ms=%s",
        len(question),
        top_k,
        len(rows),
        used_candidates,
        low_confidence,
        len(context),
        elapsed_ms,
    )

    citations = [
        RAGCitation(
            product_id=row["id"],
            sku=row["sku"],
            name=row["name"],
            score=row["score"],
        )
        for row in filtered_rows[:used_candidates]
    ]
    return RAGAnswerResponse(
        question=question,
        answer=answer,
        citations=citations,
        used_context_chars=len(context),
        total_candidates=len(rows),
        used_candidates=used_candidates,
        low_confidence=low_confidence,
    )
