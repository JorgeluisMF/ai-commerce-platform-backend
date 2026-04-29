from __future__ import annotations

import uuid
from pathlib import Path

from app.core.config import Settings


class LocalStorage:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._root = Path(settings.local_media_path)

    def put(
        self,
        *,
        product_id: int,
        data: bytes,
        extension: str,
        storage_key: str | None = None,
    ) -> str:
        safe_ext = extension.lstrip(".").lower()
        rel = (storage_key or f"{product_id}/{uuid.uuid4()}.{safe_ext}").lstrip("/")
        target = self._root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return rel.replace("\\", "/")

    def delete(self, storage_key: str) -> None:
        path = self._root / storage_key
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def public_url(self, storage_key: str) -> str:
        base = self._settings.local_media_public_base_url.rstrip("/")
        key = storage_key.lstrip("/")
        return f"{base}/{key}"
