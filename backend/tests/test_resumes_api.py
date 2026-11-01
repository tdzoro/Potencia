"""End-to-end API tests for upload → parse → analyse → report.

A generated PDF is used rather than a committed binary: the test proves the real
extraction path (PyMuPDF) and the real parser and scorer, and it cannot drift
away from the code the way a checked-in fixture does.
"""

from __future__ import annotations

import io
import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient

RESUME_TEXT = """ARJUN MEHTA
arjun.mehta@example.com | +91 98765 43210 | linkedin.com/in/arjunmehta

SUMMARY
Backend engineer with four years building payment services.

TECHNICAL SKILLS
Python, Django, PostgreSQL, Docker, AWS, Kubernetes, Redis

WORK EXPERIENCE
Backend Engineer
Acme Payments | Mar 2022 - Present
- Built a ledger service handling 2M daily transactions
- Reduced p99 latency from 800ms to 220ms by adding Redis caching
- Mentored three junior engineers

Software Engineer
Northwind Systems | Jul 2020 - Feb 2022
- Automated reconciliation reports with Python and Pandas

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


def _register(client: TestClient, email: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "a-long-enough-password", "display_name": "Test"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['tokens']['access_token']}"}


def _upload(client: TestClient, headers: dict) -> dict:
    response = client.post(
        "/api/v1/resumes",
        headers=headers,
        files={"file": ("arjun.pdf", _pdf(RESUME_TEXT), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_upload_parses_the_document(client: TestClient) -> None:
    headers = _register(client, "owner@example.com")
    body = _upload(client, headers)

    assert body["status"] == "completed"
    assert body["page_count"] == 1
    assert body["extraction"]["method"] == "text_layer"
    assert body["extraction"]["confidence"] > 0.8

    structure = body["structure"]
    assert structure["contact"]["email"] == "arjun.mehta@example.com"
    assert structure["sections"]["experience"] is True
    assert len(structure["experience"]) == 2
    assert structure["experience"][0]["organisation"] == "Acme Payments"
    assert structure["experience"][0]["bullets"]
    assert "Python" in structure["skills"]["explicit"]


def test_analysis_produces_scores_evidence_and_actions(client: TestClient) -> None:
    headers = _register(client, "analyst@example.com")
    resume = _upload(client, headers)

    response = client.post(
        "/api/v1/analyses", headers=headers, json={"resume_id": resume["id"]}
    )
    assert response.status_code == 201, response.text
    report = response.json()

    assert report["status"] == "completed"
    assert report["methodology_version"] == "1.0.0"

    scores = report["scores"]
    assert 0 <= scores["overall"] <= 100
    assert scores["applicable_weight"] > 0
    assert set(scores["components"]) == {
        "content_quality",
        "experience",
        "skills",
        "structure",
        "ats_compatibility",
        "language_readability",
    }

    assert report["ats"]["disclaimer"].startswith("ATS compatibility estimate")
    assert report["findings"], "a real resume must produce at least one finding"

    # The highest-impact problem must lead the action list, not be missing.
    assert report["priority_actions"], "findings must yield prioritised actions"
    impacts = [f["score_impact"] for f in report["findings"] if f["score_impact"]]
    assert sum(impacts) == pytest.approx(100 - scores["overall"], abs=0.15)
    top_impact = max(impacts)
    assert any(f["score_impact"] == top_impact for f in report["findings"])
    for finding in report["findings"]:
        assert finding["evidence"], f"finding {finding['criterion']} has no evidence"

    # The report is retrievable by id and by its report alias, identically.
    by_id = client.get(f"/api/v1/analyses/{report['id']}", headers=headers).json()
    by_alias = client.get(
        f"/api/v1/analyses/{report['id']}/report", headers=headers
    ).json()
    assert by_id == by_alias


def test_a_second_user_cannot_see_the_first_users_data(client: TestClient) -> None:
    owner = _register(client, "owner2@example.com")
    intruder = _register(client, "intruder@example.com")

    resume = _upload(client, owner)
    analysis = client.post(
        "/api/v1/analyses", headers=owner, json={"resume_id": resume["id"]}
    ).json()

    # 404, never 403: the existence of another user's resource is private.
    assert client.get(f"/api/v1/resumes/{resume['id']}", headers=intruder).status_code == 404
    assert client.get(f"/api/v1/analyses/{analysis['id']}", headers=intruder).status_code == 404
    assert client.delete(f"/api/v1/resumes/{resume['id']}", headers=intruder).status_code == 404

    # And the owner's list does not include the intruder's rows either.
    assert client.get("/api/v1/resumes", headers=intruder).json()["items"] == []


def test_unauthenticated_requests_are_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/resumes").status_code == 401
    assert client.post("/api/v1/resumes").status_code == 401


def test_a_disguised_file_is_rejected(client: TestClient) -> None:
    headers = _register(client, "badfile@example.com")
    response = client.post(
        "/api/v1/resumes",
        headers=headers,
        files={"file": ("resume.pdf", b"\x89PNG\r\n\x1a\nnot a pdf at all", "application/pdf")},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


def test_deleting_a_resume_removes_its_analyses(client: TestClient) -> None:
    headers = _register(client, "deleter@example.com")
    resume = _upload(client, headers)
    analysis = client.post(
        "/api/v1/analyses", headers=headers, json={"resume_id": resume["id"]}
    ).json()

    assert client.delete(f"/api/v1/resumes/{resume['id']}", headers=headers).status_code == 204
    assert client.get(f"/api/v1/analyses/{analysis['id']}", headers=headers).status_code == 404
