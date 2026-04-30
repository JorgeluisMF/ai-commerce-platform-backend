from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load env from repo root and backend root when present.
# This must work both in monorepo local paths and in deployed containers.
_CONFIG_DIR = Path(__file__).resolve().parent


def _find_backend_root(start_dir: Path) -> Path:
    current = start_dir
    while True:
        # backend root marker in this project
        if (current / "src" / "app" / "main.py").exists():
            return current
        if current.parent == current:
            return start_dir
        current = current.parent


def _find_repo_root(backend_root: Path) -> Path:
    current = backend_root
    while True:
        # monorepo marker
        if (current / "backend").exists() and (current / "frontend").exists():
            return current
        if current.parent == current:
            return backend_root
        current = current.parent


_BACKEND_ROOT = _find_backend_root(_CONFIG_DIR)
_REPO_ROOT = _find_repo_root(_BACKEND_ROOT)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", _BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="AI Commerce Platform", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    postgres_host: str = Field(..., alias="POSTGRES_HOST")
    postgres_port: int = Field(..., alias="POSTGRES_PORT", ge=1, le=65535)
    postgres_db: str = Field(..., alias="POSTGRES_DB")
    postgres_user: str = Field(..., alias="POSTGRES_USER")
    postgres_password: str = Field(..., alias="POSTGRES_PASSWORD")

    redis_host: str = Field(..., alias="REDIS_HOST")
    redis_port: int = Field(..., alias="REDIS_PORT", ge=1, le=65535)
    redis_db: int = Field(..., alias="REDIS_DB", ge=0)

    jwt_secret_key: str = Field(..., alias="JWT_SECRET_KEY", min_length=1)

    embeddings_provider: str = Field(..., alias="EMBEDDINGS_PROVIDER")
    embeddings_dimension: int = Field(..., alias="EMBEDDINGS_DIMENSION", ge=8, le=8192)

    llm_provider: str = Field(..., alias="LLM_PROVIDER")

    embeddings_enabled: bool = Field(default=True, alias="EMBEDDINGS_ENABLED")
    embeddings_async: bool = Field(
        default=False,
        alias="EMBEDDINGS_ASYNC",
        description="When true, enqueue embedding index jobs instead of synchronous indexing.",
    )
    embeddings_model: str = Field(default="text-embedding-3-small", alias="EMBEDDINGS_MODEL")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1", alias="GROQ_BASE_URL")
    llm_model: str = Field(default="llama-3.1-8b-instant", alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE")
    rag_min_score: float = Field(default=0.2, alias="RAG_MIN_SCORE")
    rag_max_context_chars: int = Field(default=3000, alias="RAG_MAX_CONTEXT_CHARS")
    rag_cache_enabled: bool = Field(default=True, alias="RAG_CACHE_ENABLED")
    rag_cache_ttl_sec: int = Field(default=120, alias="RAG_CACHE_TTL_SEC")
    rag_rate_limit_enabled: bool = Field(default=True, alias="RAG_RATE_LIMIT_ENABLED")
    rag_rate_limit_max_requests: int = Field(default=20, alias="RAG_RATE_LIMIT_MAX_REQUESTS")
    rag_rate_limit_window_sec: int = Field(default=60, alias="RAG_RATE_LIMIT_WINDOW_SEC")

    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=60, alias="JWT_EXPIRE_MINUTES")
    jwt_refresh_expire_days: int = Field(default=14, alias="JWT_REFRESH_EXPIRE_DAYS", ge=1, le=365)

    auth_rate_limit_enabled: bool = Field(default=True, alias="AUTH_RATE_LIMIT_ENABLED")
    auth_rate_limit_max_requests: int = Field(default=30, alias="AUTH_RATE_LIMIT_MAX_REQUESTS", ge=1)
    auth_rate_limit_window_sec: int = Field(default=60, alias="AUTH_RATE_LIMIT_WINDOW_SEC", ge=1)

    global_rate_limit_enabled: bool = Field(default=True, alias="GLOBAL_RATE_LIMIT_ENABLED")
    global_rate_limit_max_requests: int = Field(default=120, alias="GLOBAL_RATE_LIMIT_MAX_REQUESTS", ge=1)
    global_rate_limit_window_sec: int = Field(default=60, alias="GLOBAL_RATE_LIMIT_WINDOW_SEC", ge=1)

    idempotency_ttl_sec: int = Field(
        default=86400,
        validation_alias=AliasChoices("IDEMPOTENCY_TTL_SEC", "CHECKOUT_IDEMPOTENCY_TTL_SEC"),
        ge=60,
        description="TTL for Idempotency-Key cached responses (checkout, pay, etc.).",
    )

    simulated_payment_enabled: bool = Field(
        default=False,
        alias="SIMULATED_PAYMENT_ENABLED",
        description="Allow POST /orders/{id}/pay for non-production demos.",
    )

    forgot_password_return_token: bool = Field(
        default=False,
        alias="FORGOT_PASSWORD_RETURN_TOKEN",
        description="If true, forgot-password response includes reset_token (never use in production).",
    )
    email_backend: str = Field(
        default="console",
        alias="EMAIL_BACKEND",
        description="console | smtp",
    )
    smtp_host: str = Field(default="localhost", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT", ge=1, le=65535)
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    email_from_address: str = Field(default="noreply@localhost", alias="EMAIL_FROM_ADDRESS")
    password_reset_public_base_url: str = Field(
        default="http://localhost:5173",
        alias="PASSWORD_RESET_PUBLIC_BASE_URL",
        description="Frontend base URL used in password-reset emails.",
    )
    password_reset_ttl_sec: int = Field(
        default=3600,
        alias="PASSWORD_RESET_TTL_SEC",
        ge=60,
    )

    media_storage_backend: str = Field(
        default="local",
        alias="MEDIA_STORAGE_BACKEND",
        description="local | s3",
    )
    local_media_path: str = Field(default="./var/media", alias="LOCAL_MEDIA_PATH")
    local_media_public_base_url: str = Field(
        default="http://localhost:8000/media",
        alias="LOCAL_MEDIA_PUBLIC_BASE_URL",
        description="Base URL for LocalStorage-generated public URLs.",
    )
    s3_bucket: str | None = Field(default=None, alias="S3_BUCKET")
    s3_prefix: str = Field(default="products", alias="S3_PREFIX")
    s3_region: str | None = Field(default=None, alias="S3_REGION")
    s3_endpoint_url: str | None = Field(default=None, alias="S3_ENDPOINT_URL")
    aws_access_key_id: str | None = Field(default=None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str | None = Field(default=None, alias="AWS_SECRET_ACCESS_KEY")

    product_image_max_bytes: int = Field(
        default=2_000_000,
        alias="PRODUCT_IMAGE_MAX_BYTES",
        ge=1024,
    )
    order_currency: str = Field(default="USD", alias="ORDER_CURRENCY", min_length=3, max_length=3)
    cart_max_items_per_product: int = Field(default=999, alias="CART_MAX_ITEMS_PER_PRODUCT", ge=1)
    cart_max_lines: int = Field(default=100, alias="CART_MAX_LINES", ge=1)
    checkout_reject_on_price_mismatch: bool = Field(
        default=False,
        alias="CHECKOUT_REJECT_ON_PRICE_MISMATCH",
        description=(
            "If true, checkout returns 409 price_changed when cart line snapshot "
            "differs from current product price (after row lock)."
        ),
    )

    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        alias="CORS_ORIGINS",
        description="Comma-separated allowed origins; empty disables browser cross-origin access.",
    )
    cors_allow_credentials: bool = Field(default=True, alias="CORS_ALLOW_CREDENTIALS")
    cors_insecure_allow_any_origin: bool = Field(
        default=False,
        alias="CORS_INSECURE_ALLOW_ANY_ORIGIN",
        description="If true, allows Access-Control-Allow-Origin: * (never use in production).",
    )
    cors_allow_vercel_app: bool = Field(
        default=False,
        alias="CORS_ALLOW_VERCEL_APP",
        description=(
            "If true, also allows any https://*.vercel.app origin (Vercel previews and "
            "production on vercel.app) via CORS allow_origin_regex."
        ),
    )
    cors_extra_origin_regex: str = Field(
        default="",
        alias="CORS_EXTRA_ORIGIN_REGEX",
        description=(
            "Optional extra regex (full match against Origin) OR-combined with the Vercel pattern. "
            "Use for a custom domain, e.g. ^https://shop\\.example\\.com$"
        ),
    )
    cors_reflect_all_request_headers: bool = Field(
        default=False,
        alias="CORS_REFLECT_ALL_REQUEST_HEADERS",
        description=(
            "If true, CORS preflight mirrors any Access-Control-Request-Headers (Starlette allow_headers=['*']). "
            "Use if preflight still fails with Disallowed CORS headers."
        ),
    )
    security_x_frame_options: str = Field(default="DENY", alias="SECURITY_X_FRAME_OPTIONS")
    security_referrer_policy: str = Field(
        default="strict-origin-when-cross-origin",
        alias="SECURITY_REFERRER_POLICY",
    )

    @model_validator(mode="after")
    def validate_cors_production(self) -> "Settings":
        if self.app_env != "production":
            return self
        raw = self.cors_origins.strip()
        if self.cors_insecure_allow_any_origin or raw == "*":
            if not self.cors_insecure_allow_any_origin:
                msg = (
                    "In production, set CORS_INSECURE_ALLOW_ANY_ORIGIN=true only if you "
                    "intentionally allow wildcard CORS (strongly discouraged)."
                )
                raise ValueError(msg)
            return self
        if not raw and not self.cors_allow_vercel_app:
            msg = "CORS_ORIGINS must be set to explicit origins when APP_ENV=production"
            raise ValueError(msg)
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if not raw:
            return []
        if raw == "*":
            return ["*"]
        out: list[str] = []
        for o in raw.split(","):
            s = o.strip()
            if not s:
                continue
            while len(s) > 1 and s.endswith("/"):
                s = s[:-1]
            out.append(s)
        return out

    @property
    def cors_allow_origin_regex(self) -> str | None:
        patterns: list[str] = []
        if self.cors_allow_vercel_app:
            patterns.append(r"https://.+\.vercel\.app$")
        extra = self.cors_extra_origin_regex.strip()
        if extra:
            patterns.append(extra)
        if not patterns:
            return None
        if len(patterns) == 1:
            return patterns[0]
        return "(?:" + ")|(?:".join(patterns) + ")"

    @property
    def sqlalchemy_database_uri(self) -> str:
        return (
            "postgresql+psycopg://"
            f"{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

@lru_cache
def get_settings() -> Settings:
    return Settings()
