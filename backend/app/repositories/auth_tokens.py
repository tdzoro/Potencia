"""Authentication token persistence and cryptographic hashing.

Stores only SHA-256 digests of random tokens in the database.
Raw tokens exist in memory only during token creation or lookup.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.auth_token import AuthToken


def hash_token(raw_token: str) -> str:
    """Compute standard SHA-256 hex digest of a raw token."""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


def create_token(
    session: Session,
    *,
    user_id: uuid.UUID,
    token_type: str,
    raw_token: str,
    expires_in_seconds: int,
) -> AuthToken:
    """Record a hashed token with expiration."""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
    token = AuthToken(
        user_id=user_id,
        token_hash=hash_token(raw_token),
        token_type=token_type,
        expires_at=expires_at,
    )
    session.add(token)
    session.commit()
    session.refresh(token)
    return token


def get_token_record(
    session: Session,
    *,
    token_type: str,
    raw_token: str,
) -> AuthToken | None:
    """Look up an authentication token by type and raw token hash."""
    digest = hash_token(raw_token)
    statement = select(AuthToken).where(
        AuthToken.token_hash == digest,
        AuthToken.token_type == token_type,
    ).limit(1)
    return session.execute(statement).scalar_one_or_none()


def mark_token_used(session: Session, token: AuthToken) -> None:
    """Mark a token as consumed so it cannot be used again."""
    token.used_at = datetime.now(timezone.utc)
    session.add(token)
    session.commit()


def invalidate_pending_tokens(
    session: Session,
    *,
    user_id: uuid.UUID,
    token_type: str,
) -> None:
    """Mark all existing unconsumed tokens of this type for the user as revoked."""
    statement = (
        update(AuthToken)
        .where(
            AuthToken.user_id == user_id,
            AuthToken.token_type == token_type,
            AuthToken.used_at.is_(None),
        )
        .values(used_at=datetime.now(timezone.utc))
    )
    session.execute(statement)
    session.commit()

