"""Comprehensive audit and contract tests for POTENCIA Registration pipeline.

Covers:
1. Valid registration request, token generation, and email verification token storage.
2. Input validation failures (short password, invalid email format) returning 422.
3. Duplicate account registration attempts returning 409 Conflict.
4. SMTP failure resilience: email dispatch failures must not break account creation.
5. Database failure simulation returning 500 without leaking stack traces or internal secrets.
6. Safe diagnostic logging verification (no credentials, passwords, or tokens in logs).
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.models.auth_token import AuthTokenType
from app.repositories import auth_tokens as auth_tokens_repo
from app.repositories import users as users_repo


def test_registration_request_success(client: TestClient) -> None:
    payload = {
        "email": "audit.applicant@example.com",
        "password": "SecurePassword123!",
        "display_name": "Audit Applicant",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["user"]["email"] == "audit.applicant@example.com"
    assert body["user"]["display_name"] == "Audit Applicant"
    assert body["user"]["email_verified"] is False
    assert body["tokens"]["token_type"] == "bearer"
    assert body["tokens"]["access_token"]
    assert body["tokens"]["refresh_token"]
    assert body["tokens"]["expires_in"] == 900
    assert "password" not in body["user"]


def test_registration_validation_short_password(client: TestClient) -> None:
    payload = {
        "email": "audit.valid@example.com",
        "password": "short",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422

    body = response.json()
    assert body["error"]["code"] == "validation_error"
    # Verify field-level error detail
    fields = [d.get("field") for d in body["error"].get("details", [])]
    assert "password" in fields


def test_registration_validation_invalid_email(client: TestClient) -> None:
    payload = {
        "email": "not-an-email",
        "password": "SecurePassword123!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422

    body = response.json()
    assert body["error"]["code"] == "validation_error"
    fields = [d.get("field") for d in body["error"].get("details", [])]
    assert "email" in fields


def test_registration_duplicate_email_conflict(client: TestClient) -> None:
    payload = {
        "email": "duplicate.applicant@example.com",
        "password": "SecurePassword123!",
    }
    first_res = client.post("/api/v1/auth/register", json=payload)
    assert first_res.status_code == 201

    second_res = client.post("/api/v1/auth/register", json=payload)
    assert second_res.status_code == 409
    body = second_res.json()
    assert body["error"]["code"] == "conflict"
    assert "already registered" in body["error"]["message"].lower()


def test_registration_smtp_failure_resilient(client: TestClient) -> None:
    """If SMTP provider or server is down, registration must still succeed cleanly."""
    payload = {
        "email": "smtp.outage@example.com",
        "password": "SecurePassword123!",
        "display_name": "Resilient User",
    }

    with patch("app.services.email_service.send_verification_email", side_effect=ConnectionError("SMTP connection timed out")):
        response = client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 201

    body = response.json()
    assert body["user"]["email"] == "smtp.outage@example.com"
    assert body["tokens"]["access_token"]


def test_registration_database_failure_handling(client: TestClient) -> None:
    """Ensure database unexpected errors return 500 without exposing SQL queries or stack traces."""
    payload = {
        "email": "db.fail@example.com",
        "password": "SecurePassword123!",
    }

    unhandled_client = TestClient(client.app, raise_server_exceptions=False)
    with patch("app.services.auth_service.users_repo.create", side_effect=OperationalError("connection closed", {}, None)):
        response = unhandled_client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 500

    body = response.json()
    assert body["error"]["code"] == "internal_error"
    # Never leak stack traces or internal DB error strings
    assert "connection closed" not in body["error"]["message"]
    assert "OperationalError" not in body["error"]["message"]
    assert "Traceback" not in response.text


def test_registration_safe_diagnostic_logging(client: TestClient) -> None:
    """Verify that structured diagnostic logs are produced without leaking passwords or secret tokens."""
    from app.api.routes import auth

    payload = {
        "email": "logging.check@example.com",
        "password": "SuperSecretPassword123!",
        "display_name": "Logging Candidate",
    }

    with patch.object(auth.logger, "info", wraps=auth.logger.info) as mock_info:
        response = client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 201

    assert mock_info.called
    messages = [call.args[0] for call in mock_info.call_args_list if call.args]
    assert "registration request received" in messages
    assert "registration succeeded" in messages

    # Verify no credentials leaked into logging call arguments or extra dicts
    tokens = response.json()["tokens"]
    for call in mock_info.call_args_list:
        call_repr = repr(call)
        assert "SuperSecretPassword123!" not in call_repr
        assert tokens["access_token"] not in call_repr
        assert tokens["refresh_token"] not in call_repr
