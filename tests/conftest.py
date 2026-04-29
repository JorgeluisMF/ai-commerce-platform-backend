import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

# Required Settings variables — defined here for pytest when no full .env is available.
_TEST_ENV: dict[str, str] = {
    "APP_ENV": "test",
    "EMBEDDINGS_ENABLED": "false",
    "AUTH_RATE_LIMIT_ENABLED": "false",
    "GLOBAL_RATE_LIMIT_ENABLED": "false",
    "EMAIL_BACKEND": "console",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "ai_commerce",
    "POSTGRES_USER": "postgres",
    "POSTGRES_PASSWORD": "postgres",
    "REDIS_HOST": "localhost",
    "REDIS_PORT": "6379",
    "REDIS_DB": "0",
    "JWT_SECRET_KEY": "pytest-jwt-secret-key-do-not-use-in-production",
    "EMBEDDINGS_PROVIDER": "local",
    "EMBEDDINGS_DIMENSION": "1536",
    "LLM_PROVIDER": "local",
    "SIMULATED_PAYMENT_ENABLED": "true",
}
for _key, _val in _TEST_ENV.items():
    os.environ.setdefault(_key, _val)

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

import app.models  # noqa: E402,F401 - register SQLAlchemy models for metadata.create_all()

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _noop_audit_persist(monkeypatch: pytest.MonkeyPatch) -> None:
    """Routes use SQLite in many tests; audit uses SessionLocal (Postgres) unless patched."""

    monkeypatch.setattr(
        "app.services.audit_service.persist_audit_record",
        lambda **_kwargs: None,
    )


@pytest.fixture(autouse=True)
def _noop_rag_persist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.rag_persist_service.persist_rag_query_record",
        lambda **_kwargs: None,
    )
