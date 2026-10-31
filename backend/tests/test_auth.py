"""Authentication contract tests (docs/API.md §3.2)."""

from __future__ import annotations

from fastapi.testclient import TestClient

REGISTER = {
    "email": "arghya@example.com",
    "password": "correct horse battery",
    "display_name": "Arghya Bose",
}
VALID_PASSWORD = REGISTER["password"]


def register(client: TestClient, **overrides: str) -> dict:
    payload = {**REGISTER, **overrides}
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def login(client: TestClient, email: str = REGISTER["email"], password: str = VALID_PASSWORD) -> dict:
    return client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()


def test_register_creates_account_and_returns_tokens(client: TestClient) -> None:
    body = register(client)

    assert body["user"]["email"] == REGISTER["email"]
    assert body["user"]["display_name"] == "Arghya Bose"
    assert body["user"]["email_verified"] is False
    assert body["tokens"]["token_type"] == "bearer"
    assert body["tokens"]["expires_in"] == 900
    assert body["tokens"]["access_token"]
    assert body["tokens"]["refresh_token"]
    assert body["user"]["id"]


def test_register_normalises_email_case(client: TestClient) -> None:
    register(client, email="Arghya@Example.COM")

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "arghya@example.com", "password": VALID_PASSWORD},
    )

    assert response.status_code == 200


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    register(client)

    response = client.post("/api/v1/auth/register", json=REGISTER)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_register_rejects_short_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "short@example.com", "password": "elevenchars"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_login_returns_token_pair(client: TestClient) -> None:
    register(client)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": REGISTER["email"], "password": VALID_PASSWORD},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_in"] == 900


def test_unknown_email_and_wrong_password_are_indistinguishable(client: TestClient) -> None:
    register(client)

    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"email": REGISTER["email"], "password": "definitely-not-it"},
    )
    unknown_email = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "definitely-not-it"},
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    # Same code and message: account existence must not be observable.
    assert wrong_password.json()["error"]["code"] == unknown_email.json()["error"]["code"]
    assert wrong_password.json()["error"]["message"] == unknown_email.json()["error"]["message"]


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_me_returns_the_authenticated_account(client: TestClient) -> None:
    tokens = register(client)["tokens"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == REGISTER["email"]


def test_me_rejects_a_refresh_token_as_bearer(client: TestClient) -> None:
    tokens = register(client)["tokens"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )

    assert response.status_code == 401


def test_refresh_issues_a_new_pair(client: TestClient) -> None:
    tokens = register(client)["tokens"]

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] and body["refresh_token"]


def test_refresh_rejects_an_access_token(client: TestClient) -> None:
    tokens = register(client)["tokens"]

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]})

    assert response.status_code == 401


def test_logout_revokes_refresh_tokens(client: TestClient) -> None:
    tokens = register(client)["tokens"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204

    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401


def test_account_deletion_removes_access(client: TestClient) -> None:
    tokens = register(client)["tokens"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    assert client.delete("/api/v1/users/me", headers=headers).status_code == 204

    after = client.get("/api/v1/auth/me", headers=headers)
    assert after.status_code == 401


def test_password_hash_never_appears_in_a_response(client: TestClient) -> None:
    registered = register(client)
    tokens = registered["tokens"]
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    logged_in = client.post(
        "/api/v1/auth/login",
        json={"email": REGISTER["email"], "password": VALID_PASSWORD},
    )

    for body in (registered, me.json(), logged_in.json()):
        serialised = str(body)
        assert "password_hash" not in serialised
        assert "$2b$" not in serialised
        assert VALID_PASSWORD not in serialised
