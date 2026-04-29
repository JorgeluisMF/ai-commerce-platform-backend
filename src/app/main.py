import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.errors import error_response
from app.core.http_exceptions import api_error_detail_from_http_exception
from app.core.logging import setup_logging
from app.db.session import engine

settings = get_settings()
setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(SecurityHeadersMiddleware)

_cors_origins = settings.cors_origins_list
_use_wildcard = (
    settings.cors_insecure_allow_any_origin or (len(_cors_origins) == 1 and _cors_origins[0] == "*")
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _use_wildcard else (_cors_origins or ["http://localhost:5173"]),
    allow_credentials=False if _use_wildcard else settings.cors_allow_credentials,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID", "Accept"],
    expose_headers=["*"],
)

app.add_middleware(RequestContextMiddleware)

app.include_router(api_router, prefix=settings.api_v1_prefix)

_media_root = Path(settings.local_media_path)
_media_root.mkdir(parents=True, exist_ok=True)
app.mount(
    "/media",
    StaticFiles(directory=str(_media_root.resolve())),
    name="media",
)


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("Database error: %s", exc)
    return error_response(
        code="database_error",
        message="Unexpected database error.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, str):
        return error_response(
            code="http_error",
            message=detail,
            status_code=exc.status_code,
        )
    parsed = api_error_detail_from_http_exception(detail)
    if parsed is not None:
        code, message, error_details = parsed
        return error_response(
            code=code,
            message=message,
            details=error_details,
            status_code=exc.status_code,
        )
    return error_response(
        code="http_error",
        message="Request failed.",
        details={"detail": detail},
        status_code=exc.status_code,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)
    return error_response(
        code="internal_error",
        message="Unexpected internal server error.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@app.get("/", summary="Root endpoint")
def root() -> dict[str, str]:
    return {"message": f"{settings.app_name} running"}


@app.get("/ready", summary="Readiness probe")
def readiness_probe() -> JSONResponse:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return JSONResponse(status_code=200, content={"status": "ready"})
    except SQLAlchemyError as exc:
        logger.exception("Readiness check failed: %s", exc)
        return JSONResponse(status_code=503, content={"status": "not_ready"})
