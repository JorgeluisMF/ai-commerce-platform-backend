import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_user
from app.api.deps.global_rate_limit import enforce_global_rate_limit
from app.core.config import get_settings
from app.core.http_exceptions import raise_api_error
from app.core.security import create_access_token
from app.email.factory import get_email_backend
from app.db.redis import get_redis_client
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LogoutRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserLoginRequest,
    UserMePatchRequest,
    UserPublicResponse,
    UserRegisterRequest,
)
from app.services import auth_service
from app.services.audit_service import (
    client_ip_from_request,
    persist_audit_record,
    user_agent_from_request,
)
from app.services.password_reset_service import consume_reset_token, issue_reset_token
from app.services.refresh_token_service import (
    delete_refresh_token,
    issue_refresh_token,
    read_refresh_token_user_id,
    revoke_all_refresh_tokens_for_user,
)
from app.services.user_service import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    set_user_password,
    update_user_full_name,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

_limit_auth = enforce_global_rate_limit("auth")


@router.post(
    "/register",
    response_model=UserPublicResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    dependencies=[Depends(_limit_auth)],
)
def register_account(
    payload: UserRegisterRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),  # noqa: B008
) -> UserPublicResponse:
    user = create_user(
        db,
        email=str(payload.email),
        password=payload.password,
        full_name=payload.full_name,
    )
    ip = client_ip_from_request(request)
    ua = user_agent_from_request(request)
    background_tasks.add_task(
        persist_audit_record,
        action="user.register",
        resource_type="user",
        resource_id=str(user.id),
        user_id=user.id,
        audit_metadata=None,
        ip_address=ip,
        user_agent=ua,
    )
    return UserPublicResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and obtain tokens",
    dependencies=[Depends(_limit_auth)],
)
def login(
    payload: UserLoginRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),  # noqa: B008
) -> TokenResponse:
    ip = client_ip_from_request(request)
    ua = user_agent_from_request(request)
    user = auth_service.authenticate_user(db, email=str(payload.email), password=payload.password)
    if user is None or not user.is_active:
        background_tasks.add_task(
            persist_audit_record,
            action="login.failure",
            resource_type="auth",
            audit_metadata={"reason": "invalid_or_inactive"},
            ip_address=ip,
            user_agent=ua,
        )
        raise_api_error(
            code="invalid_credentials",
            message="Invalid credentials.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    background_tasks.add_task(
        persist_audit_record,
        action="login.success",
        resource_type="user",
        resource_id=str(user.id),
        user_id=user.id,
        ip_address=ip,
        user_agent=ua,
    )
    access, expires_in, refresh, refresh_ttl = auth_service.issue_token_pair(user)
    return TokenResponse(
        access_token=access,
        expires_in=expires_in,
        refresh_token=refresh,
        refresh_expires_in=refresh_ttl,
    )


@router.post("/refresh", response_model=TokenResponse, summary="Refresh access token")
def refresh_tokens(
    payload: RefreshTokenRequest,
    db: Session = Depends(get_db),  # noqa: B008
) -> TokenResponse:
    redis_client = get_redis_client()
    user_id = read_refresh_token_user_id(redis_client, raw_token=payload.refresh_token)
    if user_id is None:
        raise_api_error(
            code="invalid_refresh_token",
            message="Refresh token invalid or expired.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    user = get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise_api_error(
            code="invalid_refresh_token",
            message="Refresh token invalid or expired.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    delete_refresh_token(redis_client, raw_token=payload.refresh_token)

    access, expires_in = create_access_token(sub=str(user.id))
    new_refresh, ttl = issue_refresh_token(redis_client, user_id=user.id)
    return TokenResponse(
        access_token=access,
        expires_in=expires_in,
        refresh_token=new_refresh,
        refresh_expires_in=ttl,
    )


@router.post("/logout", summary="Invalidate refresh token")
def logout(payload: LogoutRequest) -> dict[str, str]:
    if payload.refresh_token:
        redis_client = get_redis_client()
        delete_refresh_token(redis_client, raw_token=payload.refresh_token)
    return {"message": "Logged out."}


@router.post("/logout-all", summary="Invalidate all refresh tokens for the current user")
def logout_all_sessions(current_user: User = Depends(get_current_user)) -> dict[str, str | int]:  # noqa: B008
    redis_client = get_redis_client()
    revoked = revoke_all_refresh_tokens_for_user(redis_client, user_id=current_user.id)
    return {"message": "All refresh sessions invalidated.", "revoked_tokens": revoked}


@router.get("/me", response_model=UserPublicResponse, summary="Current authenticated user")
def read_me(current_user: User = Depends(get_current_user)) -> UserPublicResponse:  # noqa: B008
    return UserPublicResponse.model_validate(current_user)


@router.patch("/me", response_model=UserPublicResponse, summary="Update profile")
def patch_me(
    payload: UserMePatchRequest,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> UserPublicResponse:
    updated = update_user_full_name(db, current_user.id, full_name=payload.full_name)
    assert updated is not None
    return UserPublicResponse.model_validate(updated)


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    summary="Request password reset token (stored in Redis; email sent when SMTP configured)",
)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),  # noqa: B008
    _: None = Depends(_limit_auth),
) -> ForgotPasswordResponse:
    settings = get_settings()
    user = get_user_by_email(db, str(payload.email))
    token_out: str | None = None
    if user is not None and user.is_active:
        redis_client = get_redis_client()
        raw, _ttl = issue_reset_token(redis_client, user_id=user.id)
        if settings.app_env != "production" or settings.forgot_password_return_token:
            token_out = raw
        try:
            backend = get_email_backend()
            base = settings.password_reset_public_base_url.rstrip("/")
            link = f"{base}/reset-password?token={raw}"
            backend.send(
                to=str(user.email),
                subject="Password reset request",
                body_text=(
                    "You requested a password reset.\n"
                    f"Open this link to continue (single use; expires shortly):\n{link}\n"
                ),
                body_html=f'<p>You requested a password reset.</p><p><a href="{link}">Reset your password</a></p>',
            )
        except Exception:
            logger.exception("password_reset_email_failed")
    ip = client_ip_from_request(request)
    ua = user_agent_from_request(request)
    background_tasks.add_task(
        persist_audit_record,
        action="password_reset.requested",
        resource_type="auth",
        user_id=user.id if user is not None and user.is_active else None,
        audit_metadata={"issued": user is not None and user.is_active},
        ip_address=ip,
        user_agent=ua,
    )
    msg = "If this email exists, a reset token was generated."
    return ForgotPasswordResponse(message=msg, reset_token=token_out)


@router.post("/reset-password", summary="Reset password using token from forgot-password")
def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),  # noqa: B008
    _: None = Depends(_limit_auth),
) -> dict[str, str]:
    redis_client = get_redis_client()
    user_id = consume_reset_token(redis_client, raw_token=payload.token)
    if user_id is None:
        raise_api_error(
            code="invalid_reset_token",
            message="Reset token invalid or expired.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    user = get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise_api_error(
            code="invalid_reset_token",
            message="Reset token invalid or expired.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    set_user_password(db, user, new_password=payload.new_password)
    ip = client_ip_from_request(request)
    ua = user_agent_from_request(request)
    background_tasks.add_task(
        persist_audit_record,
        action="password_reset.completed",
        resource_type="user",
        resource_id=str(user.id),
        user_id=user.id,
        ip_address=ip,
        user_agent=ua,
    )
    return {"message": "Password updated."}
