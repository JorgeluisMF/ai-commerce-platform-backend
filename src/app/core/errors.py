from collections.abc import Mapping
from typing import Any

from fastapi import status
from fastapi.responses import JSONResponse


def error_response(
    *,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> JSONResponse:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = dict(details)
    return JSONResponse(status_code=status_code, content=payload)
