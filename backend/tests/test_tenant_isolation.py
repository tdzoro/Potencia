"""Comprehensive tenant isolation security test suite.

Verifies the core architectural invariant (docs/SECURITY.md & docs/ARCHITECTURE.md §1):
Every user's resources are strictly isolated at the row level. A request by
User B for any resource owned by User A (resume, analysis, revision, recommendation,
job, match, or export) MUST return HTTP 404 (Not Found), never HTTP 200, 401, or 403,
to prevent existence enumeration and cross-account data leakage.
"""

from __future__ import annotations

import io
import pymupdf as fitz
from fastapi.testclient import TestClient

SAMPLE_RESUME = """ALICE SMITH
alice@example.com | +1 555 0199

SUMMARY
Experienced software engineer with strong Python and database skills.

EXPERIENCE
Software Engineer
TechCorp | 2021 - Present
- Built high-volume REST APIs in FastAPI
- Optimized PostgreSQL database queries
- Led sprint planning and code reviews

SKILLS
Python, PostgreSQL, FastAPI, Docker, Git

EDUCATION
B.S. in Computer Science
State University | 2017 - 2021
"""


def _make_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(40, 40, 555, 800), text, fontsize=10)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_cross_tenant_isolation_on_all_resources(client: TestClient) -> None:
    # 1. Register User A and create full hierarchy of resources
    resp_a = client.post(
        "/api/v1/auth/register",
        json={"email": "usera@example.com", "password": "PasswordForUserA123!"},
    )
    assert resp_a.status_code == 201
    token_a = resp_a.json()["tokens"]["access_token"]
    headers_a = _auth_headers(token_a)

    # User A uploads resume
    pdf_bytes = _make_pdf(SAMPLE_RESUME)
    upload_resp = client.post(
        "/api/v1/resumes",
        headers=headers_a,
        files={"file": ("alice_resume.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_resp.status_code == 201
    resume_a_id = upload_resp.json()["id"]

    # User A creates analysis
    analysis_resp = client.post(
        "/api/v1/analyses",
        headers=headers_a,
        json={"resume_id": resume_a_id},
    )
    assert analysis_resp.status_code == 201
    analysis_a_id = analysis_resp.json()["id"]

    # User A fetches recommendations
    recs_resp = client.get(
        f"/api/v1/analyses/{analysis_a_id}/recommendations",
        headers=headers_a,
    )
    assert recs_resp.status_code == 200
    recs = recs_resp.json()
    assert len(recs) > 0
    rec_a_id = recs[0]["id"]

    # User A creates a job and runs a match
    job_resp = client.post(
        "/api/v1/jobs",
        headers=headers_a,
        json={
            "title": "Backend Engineer",
            "company": "CloudInc",
            "description": "Looking for Python and PostgreSQL developer with Docker experience.",
        },
    )
    assert job_resp.status_code == 201
    job_a_id = job_resp.json()["id"]

    match_resp = client.post(
        "/api/v1/matches",
        headers=headers_a,
        json={"resume_id": resume_a_id, "job_id": job_a_id},
    )
    assert match_resp.status_code == 201
    match_a_id = match_resp.json()["id"]

    # User A generates an export
    export_resp = client.post(
        "/api/v1/exports",
        headers=headers_a,
        json={"analysis_id": analysis_a_id, "kind": "analysis_report", "format": "pdf"},
    )
    assert export_resp.status_code == 202
    export_a_id = export_resp.json()["id"]

    # 2. Register User B
    resp_b = client.post(
        "/api/v1/auth/register",
        json={"email": "userb@example.com", "password": "PasswordForUserB123!"},
    )
    assert resp_b.status_code == 201
    token_b = resp_b.json()["tokens"]["access_token"]
    headers_b = _auth_headers(token_b)

    # 3. Assert User B CANNOT view or manipulate any of User A's resources (Strict 404)

    # Resume isolation
    get_res = client.get(f"/api/v1/resumes/{resume_a_id}", headers=headers_b)
    assert get_res.status_code == 404
    assert get_res.json()["error"]["code"] == "not_found"

    del_res = client.delete(f"/api/v1/resumes/{resume_a_id}", headers=headers_b)
    assert del_res.status_code == 404

    # Revisions isolation
    rev_list = client.get(f"/api/v1/resumes/{resume_a_id}/revisions", headers=headers_b)
    assert rev_list.status_code == 404

    rev_create = client.post(
        f"/api/v1/resumes/{resume_a_id}/revisions",
        headers=headers_b,
        json={"content": {"raw_text": "Hacked content"}},
    )
    assert rev_create.status_code == 404

    # Analysis isolation
    get_ana = client.get(f"/api/v1/analyses/{analysis_a_id}", headers=headers_b)
    assert get_ana.status_code == 404
    assert get_ana.json()["error"]["code"] == "not_found"

    get_ana_recs = client.get(
        f"/api/v1/analyses/{analysis_a_id}/recommendations",
        headers=headers_b,
    )
    assert get_ana_recs.status_code == 404

    # Recommendation decision isolation
    dec_rec = client.post(
        f"/api/v1/recommendations/{rec_a_id}/decision",
        headers=headers_b,
        json={"decision": "accept"},
    )
    assert dec_rec.status_code == 404

    # Job isolation
    get_job = client.get(f"/api/v1/jobs/{job_a_id}", headers=headers_b)
    assert get_job.status_code == 404

    del_job = client.delete(f"/api/v1/jobs/{job_a_id}", headers=headers_b)
    assert del_job.status_code == 404

    # Match isolation
    get_match = client.get(f"/api/v1/matches/{match_a_id}", headers=headers_b)
    assert get_match.status_code == 404

    # Export isolation
    get_exp = client.get(f"/api/v1/exports/{export_a_id}", headers=headers_b)
    assert get_exp.status_code == 404

    del_exp = client.delete(f"/api/v1/exports/{export_a_id}", headers=headers_b)
    assert del_exp.status_code == 404

    # Cross-tenant match creation: User B cannot match their resume to User A's job
    upload_b = client.post(
        "/api/v1/resumes",
        headers=headers_b,
        files={"file": ("bob_resume.pdf", pdf_bytes, "application/pdf")},
    )
    resume_b_id = upload_b.json()["id"]

    cross_match = client.post(
        "/api/v1/matches",
        headers=headers_b,
        json={"resume_id": resume_b_id, "job_id": job_a_id},
    )
    assert cross_match.status_code == 404

    # User B cannot export User A's analysis
    cross_exp = client.post(
        "/api/v1/exports",
        headers=headers_b,
        json={"analysis_id": analysis_a_id, "kind": "analysis_report", "format": "pdf"},
    )
    assert cross_exp.status_code == 404
