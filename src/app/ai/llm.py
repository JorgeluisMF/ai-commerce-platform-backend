from __future__ import annotations

import httpx

from app.core.config import get_settings


def _local_chat_answer(question: str, context: str) -> str:
    if not context.strip():
        return (
            "I could not find relevant products with the current information. "
            "You can rephrase the question or create more products."
        )
    return (
        "Catalog-context assisted answer.\n"
        f"Question: {question.strip()}\n"
        "Tip: review cited products and validate stock/price in real time."
    )


def _groq_chat_answer(question: str, context: str) -> str:
    settings = get_settings()
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is required when LLM_PROVIDER=groq.")

    system_prompt = (
        "You are an e-commerce assistant. Answer only using the provided product context. "
        "If context is insufficient, state it explicitly."
    )
    user_prompt = (
        f"Product context:\n{context}\n\n"
        f"User question:\n{question}\n\n"
        "Respond in English, clearly and briefly."
    )

    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    with httpx.Client(timeout=45.0) as client:
        response = client.post(f"{settings.groq_base_url}/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    return data["choices"][0]["message"]["content"].strip()


def generate_rag_answer(*, question: str, context: str) -> str:
    settings = get_settings()
    provider = settings.llm_provider.lower().strip()
    if provider == "groq":
        return _groq_chat_answer(question, context)
    if provider == "local":
        return _local_chat_answer(question, context)
    msg = f"LLM_PROVIDER must be one of: local, groq (received value: {provider!r})."
    raise RuntimeError(msg)
