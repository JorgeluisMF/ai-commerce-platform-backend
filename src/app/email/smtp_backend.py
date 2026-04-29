from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.email.base import EmailBackend

logger = logging.getLogger(__name__)


class SmtpEmailBackend(EmailBackend):
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        from_address: str,
        use_tls: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from = from_address
        self._use_tls = use_tls

    def send(self, *, to: str, subject: str, body_text: str, body_html: str | None = None) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._from
        msg["To"] = to
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

        try:
            with smtplib.SMTP(self._host, self._port, timeout=30) as smtp:
                if self._use_tls:
                    smtp.starttls()
                if self._username and self._password is not None:
                    smtp.login(self._username, self._password)
                smtp.sendmail(self._from, [to], msg.as_string())
        except OSError as exc:
            logger.exception("smtp_send_failed to=%s", to)
            raise RuntimeError("SMTP delivery failed.") from exc
