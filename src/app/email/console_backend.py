from __future__ import annotations

import logging

from app.email.base import EmailBackend

logger = logging.getLogger(__name__)


class ConsoleEmailBackend(EmailBackend):
    def send(self, *, to: str, subject: str, body_text: str, body_html: str | None = None) -> None:
        logger.info(
            "email_console_outbound",
            extra={
                "to": to,
                "subject": subject,
                "body_text": body_text[:2000],
                "has_html": body_html is not None,
            },
        )
