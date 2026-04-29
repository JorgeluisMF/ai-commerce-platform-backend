import logging
import sys

from pythonjsonlogger.json import JsonFormatter

from app.core.config import get_settings
from app.core.request_context import RequestContextLogFilter


def setup_logging() -> None:
    settings = get_settings()
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestContextLogFilter())
    handler.setFormatter(
        JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s "
            "%(request_id)s %(path)s %(method)s %(duration_ms)s %(user_id)s"
        )
    )

    root_logger.handlers.clear()
    root_logger.addHandler(handler)
