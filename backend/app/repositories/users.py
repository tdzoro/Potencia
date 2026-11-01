"""User persistence.

Deliberately small: an account is looked up by id or email and written once.
Soft-deleted rows are excluded by `get_active_by_id` rather than by every caller
remembering to check, because the caller that forgets is the one that leaks.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def get_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)


def get_active_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    user = session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        return None
    return user


def get_by_email(session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email).limit(1)
    return session.execute(statement).scalar_one_or_none()


def create(
    session: Session,
    *,
    email: str,
    password_hash: str,
    display_name: str | None,
) -> User:
    user = User(email=email, password_hash=password_hash, display_name=display_name)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def mark_email_verified(session: Session, user: User) -> User:
    """Mark an account's email as verified."""
    user.email_verified = True
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def update_password(session: Session, user: User, password_hash: str) -> User:
    """Update password hash and bump token_version to invalidate all existing sessions."""
    user.password_hash = password_hash
    user.token_version = (user.token_version or 0) + 1
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def bump_token_version(session: Session, user: User) -> User:
    """Invalidate every refresh token issued to this account."""
    user.token_version = (user.token_version or 0) + 1
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def delete(session: Session, user: User) -> None:
    """Hard delete. Dependent rows are removed by `ON DELETE CASCADE`."""
    session.delete(user)
    session.commit()
