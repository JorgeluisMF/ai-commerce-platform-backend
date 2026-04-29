from collections.abc import Mapping
from typing import Any, NoReturn

from fastapi import HTTPException, status


def raise_api_error(
    *,
    code: str,
    message: str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
    details: Mapping[str, Any] | None = None,
) -> NoReturn:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        payload["details"] = dict(details)
    raise HTTPException(status_code=status_code, detail=payload) from None


def api_error_detail_from_http_exception(
    detail: Any,
) -> tuple[str, str, dict[str, Any] | None] | None:
    """
    Parse structured HTTPException detail into (code, message, optional details).
    Returns None if detail is not a structured dict with code + message.
    """
    if not isinstance(detail, dict):
        return None
    code = detail.get("code")
    message = detail.get("message")
    if not isinstance(code, str) or not isinstance(message, str):
        return None
    raw = detail.get("details")
    if raw is None:
        return code, message, None
    if isinstance(raw, dict):
        return code, message, dict(raw)
    return code, message, {"detail": raw}
