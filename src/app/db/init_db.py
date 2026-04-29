import logging

from sqlalchemy.exc import SQLAlchemyError

from app.db.base import Base
from app.db.session import engine
from app.models import Product  # noqa: F401

logger = logging.getLogger(__name__)


def init_db() -> None:
    """
    Initialize database tables for local/dev environments.
    In production, replace this with Alembic migrations.
    """
    try:
        Base.metadata.create_all(bind=engine)
    except SQLAlchemyError:
        logger.exception("Failed to initialize database tables.")
        raise
