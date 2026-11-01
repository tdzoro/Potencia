"""Named resume versions and the version comparison endpoint.

A resume is uploaded once and may carry several named versions for different
target roles. These tests cover the two things that can go wrong: a version is
saved with attributes it should not have (or without the ones it needs), and a
comparison crosses into data the caller does not own.
"""

from __future__ import annotations

import copy
import io

import fitz
from fastapi.testclient import TestClient

RESUME_TEXT = """RAHUL IYER
rahul.iyer@example.com | +91 99887 76655

SUMMARY
Full-stack developer building internal tools for operations teams.

TECHNICAL SKILLS
TypeScript, React, Node.js, PostgreSQL, Docker

WORK EXPERIENCE
Software Engineer
Lattice Works | Jun 2021 - Present
- Shipped a scheduling tool used by 400 operators
- Cut page load time from 4.1s to 900ms by splitting bundles

EDUCATION
B.Tech in Information Technology
VJTI | 2017 - 2021
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


def _resume_with_initial_revision(
    client: TestClient, headers: dict[str, str]
) -> tuple[str, dict]:
    resume = client.post(
        "/api/v1/resumes",
        headers=headers,
        files={"file": ("rahul.pdf", _pdf(RESUME_TEXT), "application/pdf")},
    ).json()
    revisions = client.get(f"/api/v1/resumes/{resume['id']}/revisions", headers=headers).json()
    assert len(revisions) == 1
    return resume["id"], revisions[0]


def _new_version(
    client: TestClient,
    headers: dict[str, str],
    resume_id: str,
    parent: dict,
    *,
    summary: str | None = None,
    label: str | None = None,
) -> dict:
    content = parent["content"]
    if summary is not None:
        content["summary"] = {"text": summary, "present": True}
    payload: dict = {"content": content, "parent_id": parent["id"]}
    if label is not None:
        payload["label"] = label
    response = client.post(
        f"/api/v1/resumes/{resume_id}/revisions", headers=headers, json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_a_version_label_is_stored_and_returned(client: TestClient) -> None:
    headers = _register(client, "versions-label@example.com")
    resume_id, base = _resume_with_initial_revision(client, headers)

    created = _new_version(
        client, headers, resume_id, base, summary="Backend-leaning full-stack engineer.", label="Backend"
    )
    assert created["label"] == "Backend"

    listed = client.get(f"/api/v1/resumes/{resume_id}/revisions", headers=headers).json()
    labels = [revision["label"] for revision in listed]
    assert labels == [None, "Backend"]


def test_an_unlabelled_version_stays_unlabelled(client: TestClient) -> None:
    headers = _register(client, "versions-unlabelled@example.com")
    resume_id, base = _resume_with_initial_revision(client, headers)

    created = _new_version(client, headers, resume_id, base, summary="Data-leaning engineer.")

    assert created["label"] is None


def test_a_malformed_parent_id_is_a_validation_error_not_a_crash(client: TestClient) -> None:
    headers = _register(client, "versions-bad-parent@example.com")
    resume_id, base = _resume_with_initial_revision(client, headers)

    response = client.post(
        f"/api/v1/resumes/{resume_id}/revisions",
        headers=headers,
        json={"content": base["content"], "parent_id": "not-a-uuid"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_a_label_longer_than_the_column_is_rejected(client: TestClient) -> None:
    headers = _register(client, "versions-long-label@example.com")
    resume_id, base = _resume_with_initial_revision(client, headers)

    response = client.post(
        f"/api/v1/resumes/{resume_id}/revisions",
        headers=headers,
        json={"content": base["content"], "parent_id": base["id"], "label": "x" * 81},
    )

    assert response.status_code == 422


def test_comparison_reports_the_field_that_changed(client: TestClient) -> None:
    headers = _register(client, "versions-compare@example.com")
    resume_id, base = _resume_with_initial_revision(client, headers)
    improved_text = "Full-stack engineer who ships internal tools and measures the result."
    second = _new_version(client, headers, resume_id, base, summary=improved_text, label="Ops")

    response = client.get(
        f"/api/v1/resumes/{resume_id}/revisions/compare",
        headers=headers,
        params={"from_revision": base["id"], "to_revision": second["id"]},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["from_revision"] == base["id"]
    assert payload["to_revision"] == second["id"]
    assert payload["to_label"] == "Ops"

    fields = {change["field"]: change for change in payload["changes"]}
    assert "summary" in fields
    assert fields["summary"]["after"] == improved_text
    assert fields["summary"]["before"] == "Full-stack developer building internal tools for operations teams."
    # Only the summary was edited, so nothing else may claim to have changed.
    assert set(fields) == {"summary"}


def test_comparing_a_version_with_itself_reports_no_changes(client: TestClient) -> None:
    headers = _register(client, "versions-identical@example.com")
    resume_id, base = _resume_with_initial_revision(client, headers)

    response = client.get(
        f"/api/v1/resumes/{resume_id}/revisions/compare",
        headers=headers,
        params={"from_revision": base["id"], "to_revision": base["id"]},
    )

    assert response.status_code == 200
    assert response.json()["changes"] == []


def test_comparison_covers_projects_and_education(client: TestClient) -> None:
    """The diff must not stop at summary and bullets.

    Projects and education are editable in the studio, so a change there has to
    appear in the comparison — otherwise a user can edit a field and be told
    nothing changed.
    """
    headers = _register(client, "versions-fields@example.com")
    resume_id, base = _resume_with_initial_revision(client, headers)

    with_project = copy.deepcopy(base["content"])
    with_project["projects"] = [
        {
            "name": "Ledger",
            "description": "Internal payments ledger.",
            "technologies": ["Python", "PostgreSQL"],
            "bullets": [{"text": "Reconciled 2M rows a day.", "span": None}],
        }
    ]
    with_project["education"][0]["details"] = ["Graduated with distinction"]
    first = client.post(
        f"/api/v1/resumes/{resume_id}/revisions",
        headers=headers,
        json={"content": with_project, "parent_id": base["id"]},
    )
    assert first.status_code == 201, first.text
    first_body = first.json()

    edited = copy.deepcopy(first_body["content"])
    edited["projects"][0]["description"] = "Ledger that reconciles vendor payouts."
    edited["projects"][0]["technologies"] = ["Python", "PostgreSQL", "Redis"]
    edited["education"][0]["degree"] = "M.Tech"
    second = client.post(
        f"/api/v1/resumes/{resume_id}/revisions",
        headers=headers,
        json={"content": edited, "parent_id": first_body["id"]},
    )
    assert second.status_code == 201, second.text

    response = client.get(
        f"/api/v1/resumes/{resume_id}/revisions/compare",
        headers=headers,
        params={"from_revision": first_body["id"], "to_revision": second.json()["id"]},
    )

    assert response.status_code == 200, response.text
    fields = {change["field"]: change for change in response.json()["changes"]}
    assert set(fields) == {
        "projects[0].description",
        "projects[0].technologies",
        "education[0].degree",
    }
    assert fields["projects[0].description"]["after"] == "Ledger that reconciles vendor payouts."
    assert fields["projects[0].technologies"]["after"] == "Python, PostgreSQL, Redis"
    assert fields["education[0].degree"]["before"] == "B.Tech"
    assert fields["education[0].degree"]["after"] == "M.Tech"


def test_one_can_compare_versions_of_a_different_resume(client: TestClient) -> None:
    """Both versions must belong to the resume in the path, not just to the caller."""
    headers = _register(client, "versions-cross@example.com")
    first_resume, first_base = _resume_with_initial_revision(client, headers)
    second_resume, _second_base = _resume_with_initial_revision(client, headers)

    foreign = client.get(
        f"/api/v1/resumes/{first_resume}/revisions",
        headers=headers,
    ).json()[0]
    other = client.get(f"/api/v1/resumes/{second_resume}/revisions", headers=headers).json()[0]

    response = client.get(
        f"/api/v1/resumes/{first_resume}/revisions/compare",
        headers=headers,
        params={"from_revision": foreign["id"], "to_revision": other["id"]},
    )

    assert response.status_code == 404


def test_another_account_cannot_compare_or_label_versions(client: TestClient) -> None:
    owner = _register(client, "versions-owner@example.com")
    intruder = _register(client, "versions-intruder@example.com")
    resume_id, base = _resume_with_initial_revision(client, owner)
    second = _new_version(client, owner, resume_id, base, summary="Owner's edit.")

    compare = client.get(
        f"/api/v1/resumes/{resume_id}/revisions/compare",
        headers=intruder,
        params={"from_revision": base["id"], "to_revision": second["id"]},
    )
    assert compare.status_code == 404

    write = client.post(
        f"/api/v1/resumes/{resume_id}/revisions",
        headers=intruder,
        json={"content": base["content"], "parent_id": base["id"], "label": "Hijack"},
    )
    assert write.status_code == 404
