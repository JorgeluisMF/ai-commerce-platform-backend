from __future__ import annotations

import hashlib
from math import sqrt

import httpx

from app.core.config import get_settings


def build_product_embedding_text(*, name: str, description: str | None, sku: str) -> str:
    description_value = description or ""
    return f"name: {name}\nsku: {sku}\ndescription: {description_value}".strip()


def _normalize_vector(vector: list[float]) -> list[float]:
    norm = sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _local_embedding(text: str, dimension: int) -> list[float]:
    vector = [0.0] * dimension
    for index in range(dimension):
        digest = hashlib.sha256(f"{text}:{index}".encode("utf-8")).digest()
        value = int.from_bytes(digest[:4], "big", signed=False)
        vector[index] = (value / 2**32) * 2 - 1
    return _normalize_vector(vector)


def _openai_embedding(text: str) -> list[float]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required when EMBEDDINGS_PROVIDER=openai.")

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": settings.embeddings_model, "input": text}
    with httpx.Client(timeout=30.0) as client:
        response = client.post(f"{settings.openai_base_url}/embeddings", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    return data["data"][0]["embedding"]


def _groq_embedding(text: str) -> list[float]:
    settings = get_settings()
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is required when EMBEDDINGS_PROVIDER=groq.")

    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": settings.embeddings_model, "input": text}
    with httpx.Client(timeout=30.0) as client:
        response = client.post(f"{settings.groq_base_url}/embeddings", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    return data["data"][0]["embedding"]


def generate_embedding(text: str) -> list[float]:
    settings = get_settings()
    provider = settings.embeddings_provider.lower().strip()
    if provider == "openai":
        vector = _openai_embedding(text)
    elif provider == "groq":
        vector = _groq_embedding(text)
    elif provider == "local":
        vector = _local_embedding(text, settings.embeddings_dimension)
    else:
        msg = (
            "EMBEDDINGS_PROVIDER debe ser uno de: local, openai, groq "
            f"(valor recibido: {provider!r})."
        )
        raise RuntimeError(msg)

    if len(vector) != settings.embeddings_dimension:
        raise RuntimeError(
            f"Embedding dimension mismatch: got={len(vector)} expected={settings.embeddings_dimension}"
        )
    return vector
