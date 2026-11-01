"""Idempotent creates (docs/API.md §1.5).

A duplicate submit is a real user behaviour — a double tap, a flaky connection, a
retried request — and it must not bill the user for the work twice.
"""

from __future__ import annotations

import io
import uuid
import pymupdf as fitz
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.idempotency import IdempotencyKey

RESUME_TEXT = """ARJUN MEHTA
arjun.mehta@example.com

SUMMARY
Backend engineer.

WORK EXPERIENCE
Backend Engineer
Acme Payments | 2022 - Present
- Built a ledger service
"""


def _pdf() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(fitz.Rect(40, 40, 555, 800), RESUME_TEXT, fontsize=9)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def _register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "a-long-enough-password", "display_name": "T"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['tokens']['access_token']}"}


def _upload(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/api/v1/resumes",
        headers=headers,
        files={"file": ("arjun.pdf", _pdf(), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_a_repeated_analysis_key_replays_and_creates_nothing(client: TestClient) -> None:
    headers = _register(client, "idem-analysis@example.com")
    resume = _upload(client, headers)
    keyed = {**headers, "X-Idempotency-Key": "analysis-key-0001"}

    first = client.post("/api/v1/analyses", headers=keyed, json={"resume_id": resume["id"]})
    assert first.status_code == 201

    second = client.post("/api/v1/analyses", headers=keyed, json={"resume_id": resume["id"]})
    assert second.status_code == 200
    assert second.headers["Idempotency-Replayed"] == "true"
    assert second.json()["id"] == first.json()["id"]

    # One analysis exists, not two.
    listed = client.get("/api/v1/analyses", headers=headers).json()
    assert len(listed["items"]) == 1


def test_a_repeated_upload_key_replays_the_original_document(client: TestClient) -> None:
    headers = _register(client, "idem-upload@example.com")
    keyed = {**headers, "X-Idempotency-Key": "upload-key-0001"}

    first = client.post(
        "/api/v1/resumes",
        headers=keyed,
        files={"file": ("arjun.pdf", _pdf(), "application/pdf")},
    )
    second = client.post(
        "/api/v1/resumes",
        headers=keyed,
        files={"file": ("arjun.pdf", _pdf(), "application/pdf")},
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert len(client.get("/api/v1/resumes", headers=headers).json()["items"]) == 1


def test_a_repeated_export_key_replays_the_same_file_record(client: TestClient) -> None:
    headers = _register(client, "idem-export@example.com")
    resume = _upload(client, headers)
    analysis = client.post(
        "/api/v1/analyses", headers=headers, json={"resume_id": resume["id"]}
    ).json()

    keyed = {**headers, "X-Idempotency-Key": "export-key-0001"}
    body = {"analysis_id": analysis["id"], "kind": "analysis_report", "format": "pdf"}

    first = client.post("/api/v1/exports", headers=keyed, json=body)
    second = client.post("/api/v1/exports", headers=keyed, json=body)
    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]

    # And the stored export is visible in the analysis' export history.
    history = client.get(f"/api/v1/analyses/{analysis['id']}/exports", headers=headers).json()
    assert [record["id"] for record in history] == [first.json()["id"]]


def test_without_a_key_each_call_creates_a_new_resource(client: TestClient) -> None:
    headers = _register(client, "idem-none@example.com")
    resume = _upload(client, headers)

    first = client.post("/api/v1/analyses", headers=headers, json={"resume_id": resume["id"]})
    second = client.post("/api/v1/analyses", headers=headers, json={"resume_id": resume["id"]})
    assert first.json()["id"] != second.json()["id"]


def test_keys_are_scoped_to_one_account(client: TestClient) -> None:
    first_user = _register(client, "idem-a@example.com")
    second_user = _register(client, "idem-b@example.com")
    resume_a = _upload(client, first_user)
    resume_b = _upload(client, second_user)

    key = "shared-key-0001"
    a = client.post(
        "/api/v1/analyses",
        headers={**first_user, "X-Idempotency-Key": key},
        json={"resume_id": resume_a["id"]},
    )
    b = client.post(
        "/api/v1/analyses",
        headers={**second_user, "X-Idempotency-Key": key},
        json={"resume_id": resume_b["id"]},
    )

    # Two accounts, one key string, two real analyses.
    assert a.status_code == 201
    assert b.status_code == 201
    assert a.json()["id"] != b.json()["id"]


def test_reusing_a_key_on_a_different_endpoint_is_refused(client: TestClient) -> None:
    headers = _register(client, "idem-cross@example.com")
    resume = _upload(client, headers)
    key = "cross-endpoint-key"

    assert (
        client.post(
            "/api/v1/analyses",
            headers={**headers, "X-Idempotency-Key": key},
            json={"resume_id": resume["id"]},
        ).status_code
        == 201
    )

    reused = client.post(
        "/api/v1/exports",
        headers={**headers, "X-Idempotency-Key": key},
        json={"analysis_id": str(uuid.uuid4()), "kind": "analysis_report", "format": "pdf"},
    )
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "conflict"


def test_an_unusable_key_is_rejected_rather_than_ignored(client: TestClient) -> None:
    headers = _register(client, "idem-short@example.com")
    response = client.post(
        "/api/v1/analyses",
        headers={**headers, "X-Idempotency-Key": "abc"},
        json={"resume_id": str(uuid.uuid4())},
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["issue"] == "invalid_length"


def test_an_expired_key_can_be_used_again(client: TestClient, session: Session) -> None:
    headers = _register(client, "idem-expiry@example.com")
    resume = _upload(client, headers)
    keyed = {**headers, "X-Idempotency-Key": "expiring-key-0001"}

    first = client.post("/api/v1/analyses", headers=keyed, json={"resume_id": resume["id"]})
    assert first.status_code == 201

    # Age the stored record past the 24-hour window.
    session.execute(
        update(IdempotencyKey).values(created_at=__import__("datetime").datetime(2020, 1, 1))
    )
    session.commit()
    assert session.scalar(select(IdempotencyKey)) is not None

    second = client.post("/api/v1/analyses", headers=keyed, json={"resume_id": resume["id"]})
    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]
