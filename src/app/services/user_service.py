import uuid

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.http_exceptions import raise_api_error
from app.core.security import hash_password
from app.models.user import User, UserRole


def get_user_by_email(db: Session, email: str) -> User | None:
    normalized = email.strip().lower()
    return db.query(User).filter(User.email == normalized).first()


def get_user_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def update_user_full_name(db: Session, user_id: uuid.UUID, *, full_name: str) -> User | None:
    user = db.get(User, user_id)
    if user is None:
        return None
    user.full_name = full_name.strip()
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def set_user_password(db: Session, user: User, *, new_password: str) -> User:
    user.hashed_password = hash_password(new_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str,
    role: UserRole = UserRole.customer,
) -> User:
    normalized_email = email.strip().lower()
    user = User(
        email=normalized_email,
        hashed_password=hash_password(password),
        full_name=full_name.strip(),
        role=role,
        is_active=True,
    )
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise_api_error(
            code="email_already_registered",
            message="An account with this email already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )
    return user
