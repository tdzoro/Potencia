"""Authentication rules and account lifecycle.

Enforces:
* Account enumeration defence: wrong passwords and unknown emails return
  identical 401s and spend comparable time via a timing equaliser hash.
  Password recovery requests return constant generic success messages.
* Session revocation without a token table: refresh tokens embed `token_version`;
  bumping it invalidates every issued refresh token at once.
* Cryptographic one-time token handling: tokens for email verification and password
  reset are stored strictly as SHA-256 hashes, with expiration and single-use tracking.
* Email verification policy: configurable enforcement gating login and protected routes.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from functools import lru_cache

import jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import PotenciaError
from app.core.security import (
    ACCESS_TOKEN_TTL,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.auth_token import AuthTokenType
from app.models.user import User
from app.repositories import auth_tokens as auth_tokens_repo
from app.repositories import users as users_repo
from app.schemas.auth import LoginRequest, RegisterRequest, TokenPair
from app.services import email_service

LOGIN_FAILED_MESSAGE = "Incorrect email or password."
INVALID_REFRESH_MESSAGE = "The refresh token is invalid or has expired."


def _is_expired(dt: datetime) -> bool:
    """Return True if dt is in the past, normalizing offset-naive datetimes from SQLite."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt < datetime.now(timezone.utc)


@lru_cache(maxsize=1)
def _timing_equaliser_hash() -> str:
    """A real bcrypt hash used to spend the same time on unknown accounts."""
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

    # Generate cryptographically secure verification token
    raw_token = secrets.token_urlsafe(32)
    settings = get_settings()
    auth_tokens_repo.create_token(
        session,
        user_id=user.id,
        token_type=AuthTokenType.EMAIL_VERIFICATION,
        raw_token=raw_token,
        expires_in_seconds=settings.verification_token_expire_hours * 3600,
    )

    # Dispatch verification email
    email_service.send_verification_email(user.email, user.display_name, raw_token)

    return user, _issue_tokens(user)


def authenticate(session: Session, payload: LoginRequest) -> TokenPair:
    email = normalise_email(str(payload.email))
    user = users_repo.get_by_email(session, email)

    if user is None or user.deleted_at is not None:
        verify_password(payload.password, _timing_equaliser_hash())
        raise PotenciaError("unauthenticated", 401, LOGIN_FAILED_MESSAGE)

    if not verify_password(payload.password, user.password_hash):
        raise PotenciaError("unauthenticated", 401, LOGIN_FAILED_MESSAGE)

    settings = get_settings()
    if settings.email_verification_required and not user.email_verified:
        raise PotenciaError(
            "email_unverified",
            403,
            "Please verify your email address before signing in.",
            [{"field": "email", "issue": "unverified"}],
        )

    return _issue_tokens(user)


def verify_email(session: Session, raw_token: str) -> User:
    """Verify an account email using a submitted one-time token."""
    token_record = auth_tokens_repo.get_token_record(
        session,
        token_type=AuthTokenType.EMAIL_VERIFICATION,
        raw_token=raw_token,
    )

    if token_record is None:
        raise PotenciaError("token_invalid", 400, "The verification link is invalid.")

    if token_record.used_at is not None:
        raise PotenciaError(
            "token_already_used",
            400,
            "This verification link has already been used.",
        )

    if _is_expired(token_record.expires_at):
        raise PotenciaError(
            "token_expired",
            400,
            "This verification link has expired. Please request a new one.",
        )

    user = users_repo.get_by_id(session, token_record.user_id)
    if user is None or user.deleted_at is not None:
        raise PotenciaError("token_invalid", 400, "The associated account was not found.")

    # Consume the token and revoke any other pending verification tokens for this user
    auth_tokens_repo.mark_token_used(session, token_record)
    auth_tokens_repo.invalidate_pending_tokens(
        session,
        user_id=user.id,
        token_type=AuthTokenType.EMAIL_VERIFICATION,
    )

    # Mark user email as verified
    updated_user = users_repo.mark_email_verified(session, user)

    # Send confirmation welcome email
    email_service.send_welcome_email(updated_user.email, updated_user.display_name)
    return updated_user


def resend_verification(session: Session, email_str: str) -> None:
    """Resend verification email, invalidating previous verification tokens."""
    email = normalise_email(email_str)
    user = users_repo.get_by_email(session, email)

    if user is None or user.deleted_at is not None:
        verify_password("dummy", _timing_equaliser_hash())
        return

    if user.email_verified:
        return

    # Invalidate previous tokens
    auth_tokens_repo.invalidate_pending_tokens(
        session,
        user_id=user.id,
        token_type=AuthTokenType.EMAIL_VERIFICATION,
    )

    raw_token = secrets.token_urlsafe(32)
    settings = get_settings()
    auth_tokens_repo.create_token(
        session,
        user_id=user.id,
        token_type=AuthTokenType.EMAIL_VERIFICATION,
        raw_token=raw_token,
        expires_in_seconds=settings.verification_token_expire_hours * 3600,
    )

    email_service.send_verification_email(user.email, user.display_name, raw_token)


def forgot_password(session: Session, email_str: str) -> None:
    """Generate a password recovery token and dispatch recovery email."""
    email = normalise_email(email_str)
    user = users_repo.get_by_email(session, email)

    if user is None or user.deleted_at is not None:
        verify_password("dummy", _timing_equaliser_hash())
        return

    # Invalidate prior reset tokens
    auth_tokens_repo.invalidate_pending_tokens(
        session,
        user_id=user.id,
        token_type=AuthTokenType.PASSWORD_RESET,
    )

    raw_token = secrets.token_urlsafe(32)
    settings = get_settings()
    auth_tokens_repo.create_token(
        session,
        user_id=user.id,
        token_type=AuthTokenType.PASSWORD_RESET,
        raw_token=raw_token,
        expires_in_seconds=settings.password_reset_token_expire_minutes * 60,
    )

    email_service.send_password_reset_email(user.email, user.display_name, raw_token)


def reset_password(session: Session, raw_token: str, new_password: str) -> None:
    """Validate recovery token, update password, and revoke all active refresh tokens."""
    token_record = auth_tokens_repo.get_token_record(
        session,
        token_type=AuthTokenType.PASSWORD_RESET,
        raw_token=raw_token,
    )

    if token_record is None:
        raise PotenciaError("token_invalid", 400, "The password reset link is invalid.")

    if token_record.used_at is not None:
        raise PotenciaError(
            "token_already_used",
            400,
            "This password reset link has already been used.",
        )

    if _is_expired(token_record.expires_at):
        raise PotenciaError(
            "token_expired",
            400,
            "This password reset link has expired. Please request a new one.",
        )

    user = users_repo.get_by_id(session, token_record.user_id)
    if user is None or user.deleted_at is not None:
        raise PotenciaError("token_invalid", 400, "The associated account was not found.")

    new_hash = hash_password(new_password)
    # update_password updates the hash AND bumps user.token_version, revoking all refresh tokens
    users_repo.update_password(session, user, new_hash)

    # Mark token used and invalidate any remaining reset tokens
    auth_tokens_repo.mark_token_used(session, token_record)
    auth_tokens_repo.invalidate_pending_tokens(
        session,
        user_id=user.id,
        token_type=AuthTokenType.PASSWORD_RESET,
    )

    email_service.send_password_changed_notification(user.email, user.display_name)


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
    users_repo.bump_token_version(session, user)


def delete_account(session: Session, user: User) -> None:
    users_repo.delete(session, user)
