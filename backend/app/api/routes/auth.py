"""Authentication endpoints (docs/API.md §3.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_user_any
from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenPair,
    UserOut,
    VerifyEmailRequest,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
# Account management shares this module so the user's own account operations
# stay beside the credentials they act on.
users_router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account, receive tokens and initiate email verification",
)
def register(payload: RegisterRequest, session: Session = Depends(get_db)) -> AuthResponse:
    user, tokens = auth_service.register(session, payload)
    return AuthResponse(user=UserOut.model_validate(user), tokens=tokens)


@router.post("/login", response_model=TokenPair, summary="Exchange credentials for tokens")
def login(payload: LoginRequest, session: Session = Depends(get_db)) -> TokenPair:
    return auth_service.authenticate(session, payload)


@router.post("/refresh", response_model=TokenPair, summary="Rotate an expired access token")
def refresh(payload: RefreshRequest, session: Session = Depends(get_db)) -> TokenPair:
    return auth_service.refresh(session, payload.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the account's refresh tokens",
)
def logout(
    current_user: User = Depends(get_current_user_any),
    session: Session = Depends(get_db),
) -> Response:
    auth_service.logout(session, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut, summary="The authenticated account")
def read_me(current_user: User = Depends(get_current_user_any)) -> UserOut:
    return UserOut.model_validate(current_user)


@router.post(
    "/verify-email",
    response_model=MessageResponse,
    summary="Verify an account email with a one-time token",
)
def verify_email(
    payload: VerifyEmailRequest,
    session: Session = Depends(get_db),
) -> MessageResponse:
    user = auth_service.verify_email(session, payload.token)
    return MessageResponse(
        message="Email verified successfully. Your account is now active.",
        email=user.email,
    )


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    summary="Resend verification link (generic response to prevent email enumeration)",
)
def resend_verification(
    payload: ResendVerificationRequest,
    session: Session = Depends(get_db),
) -> MessageResponse:
    auth_service.resend_verification(session, str(payload.email))
    return MessageResponse(
        message="If an unverified account exists for that email, a verification link has been sent.",
        email=payload.email,
    )


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Initiate password recovery (generic response to prevent email enumeration)",
)
def forgot_password(
    payload: ForgotPasswordRequest,
    session: Session = Depends(get_db),
) -> MessageResponse:
    auth_service.forgot_password(session, str(payload.email))
    return MessageResponse(
        message="If an account exists with that email address, password reset instructions have been sent.",
        email=payload.email,
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Reset password using a one-time recovery token",
)
def reset_password(
    payload: ResetPasswordRequest,
    session: Session = Depends(get_db),
) -> MessageResponse:
    auth_service.reset_password(session, payload.token, payload.new_password)
    return MessageResponse(
        message="Password has been reset successfully. Please sign in with your new password.",
    )


@users_router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete the account and everything it owns",
)
def delete_me(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Response:
    auth_service.delete_account(session, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
