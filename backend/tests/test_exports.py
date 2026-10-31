"""Export tests: the file must open, contain the real numbers, and stay private.

A generated file is not a valid file. Each test re-opens the download with a
parser and asserts on its contents, because "200 OK" says nothing about whether
the user received something usable.
"""

from __future__ import annotations

import io

import fitz
import pytest
from docx import Document as DocxDocument
from fastapi.testclient import TestClient

RESUME_TEXT = """ARJUN MEHTA
arjun.mehta@example.com | +91 98765 43210

SUMMARY
Backend engineer with four years building payment services.

TECHNICAL SKILLS
Python, Django, PostgreSQL, Docker, AWS, Kubernetes, Redis

WORK EXPERIENCE
Backend Engineer
Acme Payments | Mar 2022 - Present
- Built a ledger service handling 2M daily transactions
- Reduced p99 latency from 800ms to 220ms by adding Redis caching

EDUCATION
B.Tech in Computer Science
National Institute of Technology | 2016 - 2020
"""


def _pdf(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(fitz.Rect(40, 40, 555, 800), text, fontsize=9)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def _register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "a-long-enough-password", "display_name": "Test"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['tokens']['access_token']}"}


def _analysis(client: TestClient, headers: dict[str, str]) -> dict:
    resume = client.post(
        "/api/v1/resumes",
        headers=headers,
        files={"file": ("arjun.pdf", _pdf(RESUME_TEXT), "application/pdf")},
    ).json()
    analysis = client.post(
        "/api/v1/analyses", headers=headers, json={"resume_id": resume["id"]}
    )
    assert analysis.status_code == 201, analysis.text
    return analysis.json()


def _export(client: TestClient, headers: dict[str, str], payload: dict) -> dict:
    response = client.post("/api/v1/exports", headers=headers, json=payload)
    assert response.status_code == 202, response.text
    return response.json()


def test_analysis_report_pdf_is_readable_and_reports_the_real_score(client: TestClient) -> None:
    headers = _register(client, "report@example.com")
    analysis = _analysis(client, headers)

    record = _export(
        client,
        headers,
        {"analysis_id": analysis["id"], "kind": "analysis_report", "format": "pdf"},
    )
    assert record["status"] == "completed"
    assert record["size_bytes"] > 1000
    assert record["download_url"]

    download = client.get(record["download_url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"

    with fitz.open(stream=download.content, filetype="pdf") as document:
        assert document.page_count >= 1
        text = "\n".join(page.get_text() for page in document)

    # The headline number in the file is the stored score, not a re-computation.
    assert "POTENCIA" in text
    assert f"{analysis['scores']['overall']:.1f}" in text
    assert "ATS compatibility" in text
    assert "methodology" in text.lower()


def test_improved_resume_pdf_contains_the_parsed_content(client: TestClient) -> None:
    headers = _register(client, "resume-pdf@example.com")
    analysis = _analysis(client, headers)

    record = _export(
        client,
        headers,
        {"analysis_id": analysis["id"], "kind": "improved_resume", "format": "pdf"},
    )
    download = client.get(record["download_url"])
    assert download.status_code == 200

    with fitz.open(stream=download.content, filetype="pdf") as document:
        text = "\n".join(page.get_text() for page in document)

    assert "arjun.mehta@example.com" in text
    assert "Acme Payments" in text
    assert "Redis caching" in text


def test_improved_resume_docx_is_editable(client: TestClient) -> None:
    headers = _register(client, "resume-docx@example.com")
    analysis = _analysis(client, headers)

    record = _export(
        client,
        headers,
        {"analysis_id": analysis["id"], "kind": "improved_resume", "format": "docx"},
    )
    download = client.get(record["download_url"])
    assert download.status_code == 200

    document = DocxDocument(io.BytesIO(download.content))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "Acme Payments" in text
    assert "Python, Django, PostgreSQL" in text


def test_the_latest_approved_revision_is_what_gets_exported(client: TestClient) -> None:
    headers = _register(client, "revision-export@example.com")
    analysis = _analysis(client, headers)
    resume_id = analysis["resume_id"]

    revision = client.get(f"/api/v1/resumes/{resume_id}/revisions", headers=headers).json()[0]
    content = revision["content"]
    content["summary"] = {
        "text": "Staff-level payments engineer with a record of cutting p99 latency.",
        "present": True,
    }
    assert (
        client.post(
            f"/api/v1/resumes/{resume_id}/revisions",
            headers=headers,
            json={"content": content, "parent_id": revision["id"]},
        ).status_code
        == 201
    )

    record = _export(
        client,
        headers,
        {"analysis_id": analysis["id"], "kind": "improved_resume", "format": "pdf"},
    )
    with fitz.open(stream=client.get(record["download_url"]).content, filetype="pdf") as document:
        text = "\n".join(page.get_text() for page in document)
    assert "Staff-level payments engineer" in text


def test_a_tampered_or_foreign_token_yields_no_file(client: TestClient) -> None:
    owner = _register(client, "export-owner@example.com")
    intruder = _register(client, "export-intruder@example.com")
    analysis = _analysis(client, owner)

    record = _export(
        client,
        owner,
        {"analysis_id": analysis["id"], "kind": "analysis_report", "format": "pdf"},
    )

    # Another user cannot even see the export object.
    assert client.get(f"/api/v1/exports/{record['id']}", headers=intruder).status_code == 404

    # A forged token is rejected with the same 404 as a missing export.
    forged = record["download_url"].rsplit(".", 1)[0] + ".deadbeef"
    assert client.get(forged).status_code == 404

    # The signature is bound to the export id, so moving it to another id fails.
    other = _export(
        client,
        owner,
        {"analysis_id": analysis["id"], "kind": "improved_resume", "format": "pdf"},
    )
    moved = record["download_url"].replace(record["id"], other["id"])
    assert client.get(moved).status_code == 404


def test_report_docx_pairing_is_rejected(client: TestClient) -> None:
    headers = _register(client, "pairing@example.com")
    analysis = _analysis(client, headers)

    response = client.post(
        "/api/v1/exports",
        headers=headers,
        json={"analysis_id": analysis["id"], "kind": "analysis_report", "format": "docx"},
    )
    assert response.status_code == 422


def test_exports_require_authentication(client: TestClient) -> None:
    assert client.post("/api/v1/exports", json={}).status_code == 401
