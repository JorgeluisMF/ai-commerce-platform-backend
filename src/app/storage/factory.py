from app.core.config import Settings, get_settings
from app.storage.local import LocalStorage
from app.storage.s3_storage import S3Storage


def get_storage_backend(settings: Settings | None = None):
    settings = settings or get_settings()
    backend = (settings.media_storage_backend or "local").strip().lower()
    if backend == "s3":
        return S3Storage(settings)
    return LocalStorage(settings)
