from __future__ import annotations

import uuid

from app.core.config import Settings


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._bucket = settings.s3_bucket or ""
        self._prefix = settings.s3_prefix.strip("/").strip()
        if not self._bucket:
            msg = "S3_BUCKET must be set when MEDIA_STORAGE_BACKEND=s3"
            raise ValueError(msg)

        try:
            import boto3  # type: ignore[import-untyped]
        except ImportError as exc:
            msg = "boto3 is required for S3 storage (pip install boto3)."
            raise RuntimeError(msg) from exc

        session_kw: dict[str, object] = {}
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            session_kw["aws_access_key_id"] = settings.aws_access_key_id
            session_kw["aws_secret_access_key"] = settings.aws_secret_access_key
        if settings.s3_region:
            session_kw["region_name"] = settings.s3_region

        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            **session_kw,
        )

    def _full_key(self, relative: str) -> str:
        relative = relative.lstrip("/")
        if self._prefix:
            return f"{self._prefix}/{relative}"
        return relative

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
        key = self._full_key(rel)
        extra: dict[str, str] = {}
        content_type = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }.get(safe_ext, "application/octet-stream")
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key.replace("\\", "/")

    def delete(self, storage_key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=storage_key)

    def public_url(self, storage_key: str) -> str:
        """Virtual-hosted-style URL; override via CDN in front if needed."""
        region = self._settings.s3_region or "us-east-1"
        key = storage_key.lstrip("/")
        if self._settings.s3_endpoint_url:
            base = self._settings.s3_endpoint_url.rstrip("/")
            return f"{base}/{self._bucket}/{key}"
        return f"https://{self._bucket}.s3.{region}.amazonaws.com/{key}"
