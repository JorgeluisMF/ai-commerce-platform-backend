from sqlalchemy.orm import Session
from redis.exceptions import RedisError

from app.core.security import create_access_token, verify_password
from app.db.redis import get_redis_client
from app.models.user import User
from app.services.refresh_token_service import issue_refresh_token
from app.services.user_service import get_user_by_email


def authenticate_user(db: Session, *, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def issue_token_for_user(user: User) -> tuple[str, int]:
    return create_access_token(sub=str(user.id))


def issue_token_pair(user: User) -> tuple[str, int, str | None, int | None]:
    """Issue access token and optionally a Redis-backed refresh token."""
    access_token, expires_in = create_access_token(sub=str(user.id))
    refresh_token_str: str | None = None
    refresh_expires_in: int | None = None
    try:
        redis_client = get_redis_client()
        refresh_token_str, refresh_expires_in = issue_refresh_token(
            redis_client,
            user_id=user.id,
        )
    except RedisError:
        pass
    return access_token, expires_in, refresh_token_str, refresh_expires_in
