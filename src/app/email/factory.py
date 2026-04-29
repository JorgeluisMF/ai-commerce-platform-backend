from __future__ import annotations

from app.core.config import get_settings
from app.email.base import EmailBackend
from app.email.console_backend import ConsoleEmailBackend
from app.email.smtp_backend import SmtpEmailBackend


def get_email_backend() -> EmailBackend:
    settings = get_settings()
    backend = (settings.email_backend or "console").strip().lower()
    if backend == "smtp":
        return SmtpEmailBackend(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username or None,
            password=settings.smtp_password or None,
            from_address=settings.email_from_address,
            use_tls=settings.smtp_use_tls,
        )
    return ConsoleEmailBackend()
