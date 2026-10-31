"""Health endpoint contract tests (docs/API.md §3.1)."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.core import database

GENERATED_ID = re.compile(r"^req_[0-9a-f]{20}$")


def test_health_ok(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(database, "check_database", lambda: "ok")

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["dependencies"] == {"database": "ok"}
    assert body["version"]
    assert body["environment"] == "test"
    assert body["uptime_seconds"] >= 0
    assert body.get("error") is None


def test_health_degraded_when_database_unavailable(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(database, "check_database", lambda: "unavailable")

    response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["database"] == "unavailable"
    assert body["error"]["code"] == "dependency_unavailable"
    assert body["error"]["details"][0]["dependency"] == "database"


def test_health_generates_request_id(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(database, "check_database", lambda: "ok")

    request_id = client.get("/health").headers.get("X-Request-ID")

    assert request_id is not None
    assert GENERATED_ID.match(request_id)


def test_health_echoes_trusted_request_id(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(database, "check_database", lambda: "ok")

    response = client.get("/health", headers={"X-Request-ID": "client-supplied-id-01"})

    assert response.headers["X-Request-ID"] == "client-supplied-id-01"


def test_health_replaces_untrusted_request_id(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(database, "check_database", lambda: "ok")

    response = client.get("/health", headers={"X-Request-ID": "bad id !! spaces"})

    returned = response.headers["X-Request-ID"]
    assert returned != "bad id !! spaces"
    assert GENERATED_ID.match(returned)


def test_error_responses_use_the_documented_envelope(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]
