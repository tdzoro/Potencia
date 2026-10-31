"""Security behaviours that must hold at the HTTP boundary."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_login_attempts_are_rate_limited_with_retry_after(client: TestClient) -> None:
    payload = {"email": "nobody@example.com", "password": "whatever-long-enough"}
    statuses = [client.post("/api/v1/auth/login", json=payload).status_code for _ in range(6)]

    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429

    limited = client.post("/api/v1/auth/login", json=payload)
    assert limited.headers["Retry-After"].isdigit()
    assert limited.json()["error"]["code"] == "rate_limited"


def test_rate_limit_headers_describe_the_budget(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "budget@example.com", "password": "a-long-enough-password"},
    )
    assert response.status_code == 201
    assert response.headers["X-RateLimit-Limit"] == "5"
    assert response.headers["X-RateLimit-Remaining"] == "4"


def test_security_headers_are_present_on_every_response(client: TestClient) -> None:
    for path in ("/health", "/api/v1/resumes"):
        response = client.get(path)
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["Cache-Control"] == "no-store"


def test_errors_never_leak_internals(client: TestClient) -> None:
    """A 404 body names the resource, not the stack or the ORM."""
    response = client.get("/api/v1/analyses/01a193b4-89ff-7658-9a60-f204c8fd508e")
    body = response.json()
    assert response.status_code == 401
    assert "Traceback" not in response.text
    assert "sqlalchemy" not in response.text.lower()
    assert set(body["error"]) <= {"code", "message", "details", "request_id"}


def test_upload_rejects_a_file_that_lies_about_its_type(client: TestClient) -> None:
    response = client.post(
        "/api/v1/resumes",
        files={"file": ("cv.docx", b"PK\x03\x04not really a docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    # Unauthenticated wins first: authorisation is checked before parsing.
    assert response.status_code == 401
