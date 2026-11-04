"""Recommendations and revision history, end to end.

The two behaviours that matter here are that the engine is allowed to *ask*
rather than invent, and that an edit can never overwrite the original parse.
"""

from __future__ import annotations

import io
import pymupdf as fitz
from fastapi.testclient import TestClient

RESUME_TEXT = """ARJUN MEHTA
arjun.mehta@example.com | +91 98765 43210

SUMMARY
Backend engineer who works on payment services.

TECHNICAL SKILLS
Python, Django, PostgreSQL, Docker, AWS, Terraform

WORK EXPERIENCE
Backend Engineer
Acme Payments | Mar 2022 - Present
- Worked on a ledger service
- Helped with latency improvements
- Responsible for mentoring

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


def _analysed(client: TestClient, headers: dict[str, str]) -> tuple[dict, dict]:
    resume = client.post(
        "/api/v1/resumes",
        headers=headers,
        files={"file": ("arjun.pdf", _pdf(RESUME_TEXT), "application/pdf")},
    )
    assert resume.status_code == 201, resume.text
    body = resume.json()

    analysis = client.post(
        "/api/v1/analyses", headers=headers, json={"resume_id": body["id"]}
    )
    assert analysis.status_code == 201, analysis.text
    return body, analysis.json()


def test_recommendations_are_evidence_backed_and_idempotent(client: TestClient) -> None:
    headers = _register(client, "recs@example.com")
    _, analysis = _analysed(client, headers)

    first = client.get(
        f"/api/v1/analyses/{analysis['id']}/recommendations", headers=headers
    )
    assert first.status_code == 200, first.text
    items = first.json()
    assert items, "a resume with weak bullets must produce recommendations"

    for item in items:
        assert item["reason"], "a recommendation must explain itself"
        # Every card must leave the user with a next step: a concrete fix, or a
        # question. A diagnosis with neither is a dead end, not a recommendation.
        assert item["remediation"], item
        # A rewrite, a question, or both — never fabricated content.
        assert item["proposed_text"] is None or item["proposed_text"].strip()

    # Asking twice must not accumulate near-duplicates.
    second = client.get(
        f"/api/v1/analyses/{analysis['id']}/recommendations", headers=headers
    ).json()
    assert [row["id"] for row in second] == [row["id"] for row in items]


def test_a_metric_gap_asks_the_user_instead_of_inventing_a_number(client: TestClient) -> None:
    headers = _register(client, "metrics@example.com")
    _, analysis = _analysed(client, headers)

    items = client.get(
        f"/api/v1/analyses/{analysis['id']}/recommendations", headers=headers
    ).json()

    quantified = [item for item in items if any(p["field"] == "metric" for p in item["requires_user_input"])]
    assert quantified, "bullets with no numbers must trigger a metric question"
    for item in quantified:
        if item["proposed_text"]:
            # Any proposed rewrite must not smuggle in an unsupported figure.
            assert not any(char.isdigit() for char in item["proposed_text"])


def test_decisions_are_persisted_and_validated(client: TestClient) -> None:
    headers = _register(client, "decide@example.com")
    _, analysis = _analysed(client, headers)
    items = client.get(
        f"/api/v1/analyses/{analysis['id']}/recommendations", headers=headers
    ).json()

    accepted = client.post(
        f"/api/v1/recommendations/{items[0]['id']}/decision",
        headers=headers,
        json={"decision": "accept"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["state"] == "accepted"
    assert accepted.json()["decided_at"] is not None

    rejected = client.post(
        f"/api/v1/recommendations/{items[1]['id']}/decision",
        headers=headers,
        json={"decision": "reject"},
    )
    assert rejected.json()["state"] == "rejected"

    # Editing without text is a client error, not a silent no-op.
    assert (
        client.post(
            f"/api/v1/recommendations/{items[2]['id']}/decision",
            headers=headers,
            json={"decision": "edit"},
        ).status_code
        == 422
    )

    edited = client.post(
        f"/api/v1/recommendations/{items[2]['id']}/decision",
        headers=headers,
        json={"decision": "edit", "edited_text": "Built a ledger service on PostgreSQL"},
    )
    assert edited.json()["state"] == "edited"
    assert edited.json()["proposed_text"] == "Built a ledger service on PostgreSQL"

    # The decision survives a re-read rather than being recomputed.
    listed = client.get(
        f"/api/v1/analyses/{analysis['id']}/recommendations", headers=headers
    ).json()
    states = {row["id"]: row["state"] for row in listed}
    assert states[items[0]["id"]] == "accepted"
    assert states[items[2]["id"]] == "edited"


def test_a_second_user_cannot_decide_on_someone_elses_recommendation(client: TestClient) -> None:
    owner = _register(client, "owner-rec@example.com")
    intruder = _register(client, "intruder-rec@example.com")
    _, analysis = _analysed(client, owner)

    items = client.get(
        f"/api/v1/analyses/{analysis['id']}/recommendations", headers=owner
    ).json()

    assert (
        client.get(
            f"/api/v1/analyses/{analysis['id']}/recommendations", headers=intruder
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/recommendations/{items[0]['id']}/decision",
            headers=intruder,
            json={"decision": "accept"},
        ).status_code
        == 404
    )


def test_upload_creates_revision_zero_that_is_never_overwritten(client: TestClient) -> None:
    headers = _register(client, "rev@example.com")
    resume, _ = _analysed(client, headers)

    revisions = client.get(f"/api/v1/resumes/{resume['id']}/revisions", headers=headers)
    assert revisions.status_code == 200, revisions.text
    initial = revisions.json()
    assert len(initial) == 1
    assert initial[0]["parent_id"] is None
    original_content = initial[0]["content"]
    assert original_content["contact"]["email"] == "arjun.mehta@example.com"

    edited = dict(original_content)
    edited["summary"] = {"text": "Backend engineer targeting staff-level payments roles.", "present": True}

    created = client.post(
        f"/api/v1/resumes/{resume['id']}/revisions",
        headers=headers,
        json={
            "content": edited,
            "parent_id": initial[0]["id"],
            "applied_recommendation_ids": [],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["parent_id"] == initial[0]["id"]

    after = client.get(f"/api/v1/resumes/{resume['id']}/revisions", headers=headers).json()
    assert len(after) == 2
    # The original parse is still intact — an edit is a new node, not a rewrite.
    assert after[0]["content"] == original_content
    assert after[1]["content"]["summary"]["text"].startswith("Backend engineer targeting")


def test_a_revision_cannot_be_parented_to_another_resume(client: TestClient) -> None:
    first = _register(client, "rev-a@example.com")
    second = _register(client, "rev-b@example.com")

    resume_a, _ = _analysed(client, first)
    resume_b, _ = _analysed(client, second)

    foreign_parent = client.get(
        f"/api/v1/resumes/{resume_b['id']}/revisions", headers=second
    ).json()[0]
    content = client.get(f"/api/v1/resumes/{resume_a['id']}/revisions", headers=first).json()[0][
        "content"
    ]

    response = client.post(
        f"/api/v1/resumes/{resume_a['id']}/revisions",
        headers=first,
        json={"content": content, "parent_id": foreign_parent["id"]},
    )
    assert response.status_code == 404
