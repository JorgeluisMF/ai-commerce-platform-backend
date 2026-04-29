from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError as JWTInvalidTokenError

from app.core.config import get_settings


def hash_password(plain: str) -> str:
    plain_bytes = plain.encode("utf-8")
    if len(plain_bytes) > 72:
        plain_bytes = plain_bytes[:72]
    digest = bcrypt.hashpw(plain_bytes, bcrypt.gensalt())
    return digest.decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    plain_bytes = plain.encode("utf-8")
    if len(plain_bytes) > 72:
        plain_bytes = plain_bytes[:72]
    try:
        return bcrypt.checkpw(plain_bytes, hashed.encode("ascii"))
    except ValueError:
        return False


def create_access_token(*, sub: str, expires_delta: timedelta | None = None) -> tuple[str, int]:
    settings = get_settings()
    delta = (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.jwt_expire_minutes)
    )
    expire = datetime.now(UTC) + delta
    expires_in = max(0, int((expire - datetime.now(UTC)).total_seconds()))
    payload: dict[str, object] = {"sub": sub, "exp": expire}
    token = jwt.encode(
        payload,
        settings.jwt_secret_key or "",
        algorithm=settings.jwt_algorithm,
    )
    if not isinstance(token, str):
        token = token.decode("utf-8")
    return token, expires_in


def decode_access_token(token: str) -> dict[str, object]:
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret_key or "",
        algorithms=[settings.jwt_algorithm],
    )


class TokenValidationError(Exception):
    pass


def decode_token_subject(token: str) -> str:
    try:
        payload = decode_access_token(token)
    except JWTInvalidTokenError as exc:
        raise TokenValidationError from exc
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub.strip():
        raise TokenValidationError
    return sub
