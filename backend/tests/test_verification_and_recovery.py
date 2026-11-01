"""Automated test suite for Phase 23: Email Verification and Secure Password Recovery.

Covers:
- Registration dispatches verification email and stores SHA-256 hashed token.
- Valid email verification marks email_verified=True and token as used.
- Expired and already-used verification tokens rejected with 400.
- Resending verification invalidates previous pending tokens and issues new one.
- Resending verification and forgot password return generic responses (anti-enumeration).
- Password reset updates bcrypt hash and increments user.token_version.
- Session revocation: prior refresh tokens are rejected after password reset.
- Expired, already-used, or short (< 12 char) password reset attempts rejected.
- Raw tokens are never persisted in PostgreSQL / SQLite database.
- Enforcement of email_verification_required on login and protected routes.
- Graceful degradation when SMTP delivery fails.
- Rate limiting on sensitive auth endpoints.
"""

from __future__ import annotations

import re
import smtplib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.auth_token import AuthToken, AuthTokenType
from app.models.user import User
from app.repositories.auth_tokens import hash_token
from app.services.email_service import clear_sent_emails, get_sent_emails


@pytest.fixture(autouse=True)
def _clear_emails_before_each_test() -> None:
    clear_sent_emails()
    yield
    clear_sent_emails()


def _extract_token_from_email(content: str) -> str:
    """Extract token parameter from email link."""
    match = re.search(r"token=([a-zA-Z0-9_-]+)", content)
    assert match is not None, f"Could not find token in email content: {content}"
    return match.group(1)


def test_registration_dispatches_verification_email_and_hashes_token(
    client: TestClient, session: Session
) -> None:
    payload = {
        "email": "fresh-candidate@example.com",
        "password": "CorrectHorseBatteryStaple123!",
        "display_name": "Fresh Candidate",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text

    user = session.query(User).filter_by(email="fresh-candidate@example.com").first()
    assert user is not None
    assert user.email_verified is False

    emails = get_sent_emails()
    assert len(emails) == 1
    email = emails[0]
    assert email.to_email == "fresh-candidate@example.com"
    assert "Verify your POTENCIA account" in email.subject

    token = _extract_token_from_email(email.plain_content)
    assert len(token) >= 32

    # Verify database record stores the SHA-256 hash, NEVER the raw token
    expected_hash = hash_token(token)
    token_rec = (
        session.query(AuthToken)
        .filter_by(user_id=user.id, token_type=AuthTokenType.EMAIL_VERIFICATION)
        .first()
    )
    assert token_rec is not None
    assert token_rec.token_hash == expected_hash
    assert token_rec.token_hash != token
    assert token_rec.used_at is None


def test_verify_email_success(client: TestClient, session: Session) -> None:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "verify-me@example.com",
            "password": "CorrectHorseBatteryStaple123!",
        },
    )
    token = _extract_token_from_email(get_sent_emails()[0].plain_content)

    resp = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert resp.status_code == 200
    assert "Email verified successfully" in resp.json()["message"]

    session.expire_all()
    user = session.query(User).filter_by(email="verify-me@example.com").first()
    assert user is not None
    assert user.email_verified is True

    token_rec = (
        session.query(AuthToken)
        .filter_by(token_hash=hash_token(token))
        .first()
    )
    assert token_rec is not None
    assert token_rec.used_at is not None


def test_verify_email_expired_token(client: TestClient, session: Session) -> None:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "expired-verify@example.com",
            "password": "CorrectHorseBatteryStaple123!",
        },
    )
    token = _extract_token_from_email(get_sent_emails()[0].plain_content)

    # Manually expire the token in database
    token_rec = (
        session.query(AuthToken)
        .filter_by(token_hash=hash_token(token))
        .first()
    )
    assert token_rec is not None
    token_rec.expires_at = datetime.now(timezone.utc) - timedelta(hours=2)
    session.commit()

    resp = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "token_expired"

    session.expire_all()
    user = session.query(User).filter_by(email="expired-verify@example.com").first()
    assert user is not None
    assert user.email_verified is False


def test_verify_email_already_used_token(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "used-verify@example.com",
            "password": "CorrectHorseBatteryStaple123!",
        },
    )
    token = _extract_token_from_email(get_sent_emails()[0].plain_content)

    # First attempt: succeeds
    resp1 = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert resp1.status_code == 200

    # Second attempt: fails with token_already_used
    resp2 = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert resp2.status_code == 400
    assert resp2.json()["error"]["code"] == "token_already_used"


def test_verify_email_invalid_token(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/verify-email", json={"token": "totally-fabricated-token-12345"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "token_invalid"


def test_resend_verification_invalidates_previous_and_sends_new(
    client: TestClient, session: Session
) -> None:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "resend-user@example.com",
            "password": "CorrectHorseBatteryStaple123!",
        },
    )
    token_1 = _extract_token_from_email(get_sent_emails()[0].plain_content)

    # Resend verification
    resp = client.post(
        "/api/v1/auth/resend-verification", json={"email": "resend-user@example.com"}
    )
    assert resp.status_code == 200

    emails = get_sent_emails()
    assert len(emails) == 2
    token_2 = _extract_token_from_email(emails[1].plain_content)
    assert token_1 != token_2

    # Old token 1 should be marked used / invalidated
    resp_old = client.post("/api/v1/auth/verify-email", json={"token": token_1})
    assert resp_old.status_code == 400
    assert resp_old.json()["error"]["code"] == "token_already_used"

    # New token 2 successfully verifies
    resp_new = client.post("/api/v1/auth/verify-email", json={"token": token_2})
    assert resp_new.status_code == 200

    session.expire_all()
    user = session.query(User).filter_by(email="resend-user@example.com").first()
    assert user is not None
    assert user.email_verified is True


def test_resend_verification_nonexistent_email_generic_response(
    client: TestClient,
) -> None:
    resp = client.post(
        "/api/v1/auth/resend-verification", json={"email": "nonexistent@example.com"}
    )
    assert resp.status_code == 200
    assert "verification link has been sent" in resp.json()["message"]
    # No email sent
    assert len(get_sent_emails()) == 0


def test_resend_verification_already_verified_email_generic_response(
    client: TestClient,
) -> None:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "already-verified@example.com",
            "password": "CorrectHorseBatteryStaple123!",
        },
    )
    token = _extract_token_from_email(get_sent_emails()[0].plain_content)
    client.post("/api/v1/auth/verify-email", json={"token": token})
    clear_sent_emails()

    # Request resend for already verified account
    resp = client.post(
        "/api/v1/auth/resend-verification",
        json={"email": "already-verified@example.com"},
    )
    assert resp.status_code == 200
    assert "verification link has been sent" in resp.json()["message"]
    # No new email dispatched
    assert len(get_sent_emails()) == 0


def test_forgot_password_and_reset_flow(
    client: TestClient, session: Session
) -> None:
    email = "forgotten@example.com"
    old_pw = "OldSecurePassword123!"
    new_pw = "NewSuperSecurePassword456!"

    client.post("/api/v1/auth/register", json={"email": email, "password": old_pw})
    clear_sent_emails()

    # Request password recovery
    resp = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert resp.status_code == 200
    assert "password reset instructions have been sent" in resp.json()["message"]

    emails = get_sent_emails()
    assert len(emails) == 1
    reset_email = emails[0]
    assert reset_email.to_email == email
    assert "Reset your POTENCIA password" in reset_email.subject

    token = _extract_token_from_email(reset_email.plain_content)

    # Perform password reset
    reset_resp = client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": new_pw}
    )
    assert reset_resp.status_code == 200
    assert "reset successfully" in reset_resp.json()["message"].lower()

    # Verify old password fails
    bad_login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": old_pw}
    )
    assert bad_login.status_code == 401

    # Verify new password succeeds
    good_login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": new_pw}
    )
    assert good_login.status_code == 200
    assert "access_token" in good_login.json()


def test_forgot_password_nonexistent_email_generic_response(
    client: TestClient,
) -> None:
    resp = client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    assert resp.status_code == 200
    assert "password reset instructions have been sent" in resp.json()["message"]
    assert len(get_sent_emails()) == 0


def test_password_reset_revokes_active_refresh_sessions(
    client: TestClient, session: Session
) -> None:
    email = "session-revocation@example.com"
    pw = "InitialPassword123!"
    reg_resp = client.post(
        "/api/v1/auth/register", json={"email": email, "password": pw}
    )
    refresh_token = reg_resp.json()["tokens"]["refresh_token"]

    # Prior refresh token is valid
    refresh_resp_1 = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert refresh_resp_1.status_code == 200
    new_refresh = refresh_resp_1.json()["refresh_token"]

    # Initiate and complete password reset
    client.post("/api/v1/auth/forgot-password", json={"email": email})
    reset_token = _extract_token_from_email(get_sent_emails()[-1].plain_content)
    client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "CompletelyNewPassword123!"},
    )

    # Prior refresh token must now be rejected because token_version was incremented
    stale_refresh = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": new_refresh}
    )
    assert stale_refresh.status_code == 401


def test_password_reset_expired_token(client: TestClient, session: Session) -> None:
    email = "expired-reset@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "OriginalPassword123!"},
    )
    client.post("/api/v1/auth/forgot-password", json={"email": email})
    token = _extract_token_from_email(get_sent_emails()[-1].plain_content)

    # Expire token in database
    token_rec = (
        session.query(AuthToken)
        .filter_by(token_hash=hash_token(token))
        .first()
    )
    assert token_rec is not None
    token_rec.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    session.commit()

    resp = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "NewValidPassword123!"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "token_expired"


def test_password_reset_already_used_token(client: TestClient) -> None:
    email = "used-reset@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "OriginalPassword123!"},
    )
    client.post("/api/v1/auth/forgot-password", json={"email": email})
    token = _extract_token_from_email(get_sent_emails()[-1].plain_content)

    resp1 = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "BrandNewPassword123!"},
    )
    assert resp1.status_code == 200

    resp2 = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "AnotherNewPassword123!"},
    )
    assert resp2.status_code == 400
    assert resp2.json()["error"]["code"] == "token_already_used"


def test_password_reset_short_password_rejected(client: TestClient) -> None:
    email = "short-pw@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "OriginalPassword123!"},
    )
    client.post("/api/v1/auth/forgot-password", json={"email": email})
    token = _extract_token_from_email(get_sent_emails()[-1].plain_content)

    resp = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "short"},
    )
    assert resp.status_code == 422


def test_email_verification_required_blocks_unverified_login(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "email_verification_required", True)

    email = "must-verify@example.com"
    pw = "SuperSecurePassword123!"
    client.post("/api/v1/auth/register", json={"email": email, "password": pw})

    # Login rejected before verification
    login_resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": pw}
    )
    assert login_resp.status_code == 403
    assert login_resp.json()["error"]["code"] == "email_unverified"

    # Verify email
    token = _extract_token_from_email(get_sent_emails()[-1].plain_content)
    verify_resp = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert verify_resp.status_code == 200

    # Login allowed after verification
    good_login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": pw}
    )
    assert good_login.status_code == 200
    assert "access_token" in good_login.json()


def test_email_verification_required_blocks_protected_routes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "email_verification_required", True)

    email = "blocked-protected@example.com"
    pw = "SuperSecurePassword123!"
    reg_resp = client.post("/api/v1/auth/register", json={"email": email, "password": pw})
    access_token = reg_resp.json()["tokens"]["access_token"]

    # Calling protected endpoint with unverified user token yields 403 email_unverified
    prot_resp = client.get(
        "/api/v1/resumes",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert prot_resp.status_code == 403
    assert prot_resp.json()["error"]["code"] == "email_unverified"


def test_smtp_failure_handled_gracefully_on_register(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _mock_smtp(*args, **kwargs):
        raise smtplib.SMTPException("SMTP host unreachable test")

    monkeypatch.setattr(get_settings(), "smtp_host", "mail.example.com")
    monkeypatch.setattr("smtplib.SMTP", _mock_smtp)

    # Registration should still succeed and not crash with 500
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "smtp-down@example.com",
            "password": "PasswordWithGoodLength123!",
        },
    )
    assert resp.status_code == 201
    assert "tokens" in resp.json()


def test_rate_limiting_on_auth_endpoints(client: TestClient) -> None:
    # 10 requests allowed per 15 min for /verify-email; 11th should be rate-limited
    for _ in range(10):
        client.post("/api/v1/auth/verify-email", json={"token": "some-random-invalid-token"})

    rate_limited_resp = client.post(
        "/api/v1/auth/verify-email", json={"token": "some-random-invalid-token"}
    )
    assert rate_limited_resp.status_code == 429
    assert rate_limited_resp.json()["error"]["code"] == "rate_limited"
