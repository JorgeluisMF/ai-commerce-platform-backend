"""Focused checks for production-hardening behavior (plan P0–P2)."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.schemas.product import ProductSemanticSearchResponse, SemanticSearchPaginationMeta


def test_global_rate_limit_returns_429_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GLOBAL_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("GLOBAL_RATE_LIMIT_MAX_REQUESTS", "2")
    monkeypatch.setenv("GLOBAL_RATE_LIMIT_WINDOW_SEC", "60")
    get_settings.cache_clear()
    hdrs = {"X-Forwarded-For": "198.51.100.42"}
    try:
        client = TestClient(app)
        for _ in range(2):
            r = client.get("/api/v1/products?page=1&page_size=5", headers=hdrs)
            assert r.status_code == 200
        r3 = client.get("/api/v1/products?page=1&page_size=5", headers=hdrs)
        assert r3.status_code == 429
        assert r3.json()["error"]["code"] == "rate_limited"
    finally:
        monkeypatch.setenv("GLOBAL_RATE_LIMIT_ENABLED", "false")
        get_settings.cache_clear()


def test_semantic_search_response_meta_schema() -> None:
    meta = SemanticSearchPaginationMeta(total=2, page=1, page_size=5, pages=1)
    sample = ProductSemanticSearchResponse(query="x", limit=5, items=[], meta=meta)
    assert sample.meta.pages == 1
