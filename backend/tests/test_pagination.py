"""Keyset pagination for list endpoints (docs/API.md §3.3–§3.4)."""

from __future__ import annotations

import io
import pymupdf as fitz
from fastapi.testclient import TestClient

RESUME_TEXT = """ARJUN MEHTA
arjun.mehta@example.com

WORK EXPERIENCE
Backend Engineer
Acme Payments | 2022 - Present
- Built a ledger service
"""


def _pdf(label: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(fitz.Rect(40, 40, 555, 800), f"{label}\n{RESUME_TEXT}", fontsize=9)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def _register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "a-long-enough-password"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['tokens']['access_token']}"}


def _upload(client: TestClient, headers: dict[str, str], label: str) -> dict:
    response = client.post(
        "/api/v1/resumes",
        headers=headers,
        files={"file": (f"{label}.pdf", _pdf(label), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_resume_pages_walk_without_gaps_or_repeats(client: TestClient) -> None:
    headers = _register(client, "pages@example.com")
    for label in ("alpha", "bravo", "charlie"):
        _upload(client, headers, label)

    first = client.get("/api/v1/resumes?limit=2", headers=headers).json()
    assert len(first["items"]) == 2
    assert first["has_more"] is True
    assert first["next_cursor"]

    second = client.get(
        f"/api/v1/resumes?limit=2&cursor={first['next_cursor']}", headers=headers
    ).json()
    assert len(second["items"]) == 1
    assert second["has_more"] is False
    assert second["next_cursor"] is None

    seen = [item["id"] for item in first["items"] + second["items"]]
    assert len(seen) == len(set(seen)) == 3

    # Newest first: charlie was uploaded last.
    assert first["items"][0]["original_filename"] == "charlie.pdf"


def test_analysis_pages_use_the_same_contract(client: TestClient) -> None:
    headers = _register(client, "pages-analysis@example.com")
    resume = _upload(client, headers, "delta")
    for _ in range(3):
        assert (
            client.post(
                "/api/v1/analyses", headers=headers, json={"resume_id": resume["id"]}
            ).status_code
            == 201
        )

    first = client.get("/api/v1/analyses?limit=2", headers=headers).json()
    assert len(first["items"]) == 2
    assert first["has_more"] is True

    second = client.get(
        f"/api/v1/analyses?limit=2&cursor={first['next_cursor']}", headers=headers
    ).json()
    assert len(second["items"]) == 1
    assert second["has_more"] is False


def test_a_malformed_cursor_is_a_validation_error(client: TestClient) -> None:
    headers = _register(client, "pages-bad@example.com")
    response = client.get("/api/v1/resumes?cursor=not-a-cursor", headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
