from __future__ import annotations

from abc import ABC, abstractmethod


class EmailBackend(ABC):
    @abstractmethod
    def send(self, *, to: str, subject: str, body_text: str, body_html: str | None = None) -> None:
        """Deliver one message."""
