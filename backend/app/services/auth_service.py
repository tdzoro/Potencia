"""Authentication rules.

Two security properties are enforced here rather than in the routes:

* Account enumeration. A wrong password and an unknown email produce the same
  status, code and message, and take the same time — an unknown email still runs
  a bcrypt verification against a dummy hash, so the response time does not
  reveal whether the account exists.
* Session revocation without a token table. Refresh tokens embed the account's
  `token_version`; bumping it invalidates every issued refresh token at once.
"""

from __future__ import annotations

import uuid
from functools import lru_cache

import jwt
from sqlalchemy.orm import Session

from app.core.errors import PotenciaError
from app.core.security import (
    ACCESS_TOKEN_TTL,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories import users as users_repo
from app.schemas.auth import LoginRequest, RegisterRequest, TokenPair

LOGIN_FAILED_MESSAGE = "Incorrect email or password."
INVALID_REFRESH_MESSAGE = "The refresh token is invalid or has expired."


@lru_cache(maxsize=1)
def _timing_equaliser_hash() -> str:
    """A real bcrypt hash used to spend the same time on unknown accounts.

    Computed once: hashing on every failed login would double the cost of the
    exact endpoint an attacker hammers.
    """
    return hash_password("timing-equaliser-not-a-real-password")


def normalise_email(email: str) -> str:
    return email.strip().lower()


def _issue_tokens(user: User) -> TokenPair:
    subject = str(user.id)
    return TokenPair(
        access_token=create_access_token(subject),
        refresh_token=create_refresh_token(subject, user.token_version),
        expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
    )


def register(session: Session, payload: RegisterRequest) -> tuple[User, TokenPair]:
    email = normalise_email(str(payload.email))

    if users_repo.get_by_email(session, email) is not None:
        # 409 rather than a silent success: a duplicate registration must be
        # visible, or a user ends up with an account they cannot log into.
        raise PotenciaError(
            "conflict",
            409,
            "That email address is already registered.",
        )

    user = users_repo.create(
        session,
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip() if payload.display_name else None,
    )
    return user, _issue_tokens(user)


def authenticate(session: Session, payload: LoginRequest) -> TokenPair:
    email = normalise_email(str(payload.email))
    user = users_repo.get_by_email(session, email)

    if user is None or user.deleted_at is not None:
        # Spend comparable time, then fail identically.
        verify_password(payload.password, _timing_equaliser_hash())
        raise PotenciaError("unauthenticated", 401, LOGIN_FAILED_MESSAGE)

    if not verify_password(payload.password, user.password_hash):
        raise PotenciaError("unauthenticated", 401, LOGIN_FAILED_MESSAGE)

    return _issue_tokens(user)


def refresh(session: Session, refresh_token: str) -> TokenPair:
    try:
        claims = decode_token(refresh_token, "refresh")
        user_id = uuid.UUID(str(claims["sub"]))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise PotenciaError("unauthenticated", 401, INVALID_REFRESH_MESSAGE) from exc

    user = users_repo.get_active_by_id(session, user_id)
    if user is None:
        raise PotenciaError("unauthenticated", 401, INVALID_REFRESH_MESSAGE)

    if int(claims.get("ver", 0)) != int(user.token_version):
        raise PotenciaError(
            "unauthenticated",
            401,
            "This session has been revoked. Sign in again.",
        )

    return _issue_tokens(user)


def logout(session: Session, user: User) -> None:
    """Revoke the account's sessions.

    There is no per-token record yet, so this invalidates every refresh token
    for the account rather than only the presented one. Access tokens expire on
    their own within 15 minutes. Narrowing this to a single session requires a
    refresh-token table, which is deliberately deferred.
    """
    users_repo.bump_token_version(session, user)


def delete_account(session: Session, user: User) -> None:
    users_repo.delete(session, user)
