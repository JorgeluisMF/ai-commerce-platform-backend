from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.redis import get_redis_client
from app.db.session import engine

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Health check")
def health_check() -> dict[str, str | dict[str, str]]:
    """
    Returns 200 with status `ok` or `degraded` when a dependency is unavailable.
    Suitable for Kubernetes liveness/readiness without failing the probe when Redis is optional.
    """
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db_status = "error"

    redis_status = "ok"
    try:
        get_redis_client().ping()
    except Exception:
        redis_status = "error"

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    return {
        "status": overall,
        "services": {"db": db_status, "redis": redis_status},
    }
