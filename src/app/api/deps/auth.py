import uuid
from collections.abc import AsyncGenerator, Callable

from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.http_exceptions import raise_api_error
from app.core.request_context import user_id_ctx
from app.core.security import TokenValidationError, decode_token_subject
from app.db.session import get_db
from app.models.user import User, UserRole
from app.services.user_service import get_user_by_id

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> AsyncGenerator[User, None]:
    if credentials is None:
        raise_api_error(
            code="unauthorized",
            message="Not authenticated.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    token = credentials.credentials
    try:
        sub = decode_token_subject(token)
        user_id = uuid.UUID(sub)
    except (TokenValidationError, ValueError):
        raise_api_error(
            code="invalid_token",
            message="Invalid or expired token.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    user = get_user_by_id(db, user_id)
    if user is None:
        raise_api_error(
            code="invalid_token",
            message="Invalid or expired token.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if not user.is_active:
        raise_api_error(
            code="inactive_user",
            message="User account is inactive.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    uid_token = user_id_ctx.set(str(user.id))
    try:
        yield user
    finally:
        user_id_ctx.reset(uid_token)


def require_role(required: UserRole) -> Callable[..., User]:
    def _require(user: User = Depends(get_current_user)) -> User:  # noqa: B008
        if user.role != required:
            raise_api_error(
                code="forbidden",
                message="Insufficient permissions.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        return user

    return _require
