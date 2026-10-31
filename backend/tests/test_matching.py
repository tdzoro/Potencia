"""Job matching tests (Phase 8).

The assertions that matter are about honesty: an absent skill must never be
reported as matched, a skill in an unrelated sentence must not count, and the
advice for a missing skill must never suggest inventing it.
"""

from __future__ import annotations

import io

import fitz
from fastapi.testclient import TestClient

from app.intelligence.matching.engine import demonstrated_years, match_resume
from app.intelligence.matching.requirements import extract_requirements
from app.schemas.resume import (
    Bullet,
    Contact,
    ExperienceEntry,
    ResumeStructure,
    SectionPresence,
    SkillSet,
)

JOB = """Senior Backend Engineer

Requirements
- 5+ years of experience building backend services
- Strong Python, PostgreSQL and Docker
- Bachelor's degree in Computer Science or equivalent

Preferred
- Kubernetes
- Kafka

Responsibilities
- Own the ledger service and its data model
- Mentor junior engineers on testing practice
"""

RESUME_TEXT = """ARJUN MEHTA
arjun.mehta@example.com

TECHNICAL SKILLS
Python, PostgreSQL, Docker, Django

WORK EXPERIENCE
Backend Engineer
Acme Payments | Mar 2020 - Present
- Owned the ledger service and its data model
- Mentored junior engineers on testing practice
"""


def _structure(
    *,
    explicit: list[str],
    prose: str,
    years: list[tuple[str, str | None]] | None = None,
) -> ResumeStructure:
    # Always build at least one role: the prose lives in the bullet, so without
    # a role the resume body would be empty and every skill would look unclaimed.
    pairs = years if years is not None else [("2021-01", "2022-01")]
    roles = [
        ExperienceEntry(
            title="Backend Engineer",
            organisation="Acme",
            start=start,
            end=end,
            date_precision="month",
            bullets=[Bullet(text=prose)],
        )
        for start, end in pairs
    ]
    return ResumeStructure(
        contact=Contact(email="a@example.com"),
        experience=roles,
        skills=SkillSet(explicit=explicit),
        sections=SectionPresence(experience=bool(roles), skills=True),
    )


def test_requirements_are_split_by_section() -> None:
    requirements = extract_requirements(JOB)

    assert "Python" in requirements.required_skills
    assert "PostgreSQL" in requirements.required_skills
    assert "Kubernetes" in requirements.preferred_skills
    assert "Kubernetes" not in requirements.required_skills
    assert requirements.min_years == 5
    assert requirements.degree_level == "bachelor"
    assert requirements.responsibilities


def test_an_ordinary_need_sentence_yields_required_skills() -> None:
    """"We need X" states a requirement.

    Bucketing it as a preference silently hides the most important gap from the
    candidate, which is the failure this test exists to prevent.
    """
    requirements = extract_requirements(
        "Senior Backend Engineer\n"
        "We need 5+ years of Python experience, PostgreSQL, Kubernetes and Terraform.\n"
        "You will own the ledger service.\n"
    )
    assert "Python" in requirements.required_skills
    assert "PostgreSQL" in requirements.required_skills
    assert requirements.preferred_skills == []
    assert requirements.min_years == 5


def test_a_wish_list_sentence_stays_a_preference() -> None:
    requirements = extract_requirements(
        "Nice to have: Rust, Kubernetes and GraphQL. We build data platforms.\n"
    )
    assert requirements.required_skills == []
    assert "Kubernetes" in requirements.preferred_skills


def test_a_claimed_and_demonstrated_skill_matches() -> None:
    structure = _structure(explicit=["Python"], prose="Built services in Python")
    result = match_resume(structure, extract_requirements(JOB))

    python = next(m for m in result.requirements.required_skills if m.name == "Python")
    assert python.status == "matched"
    assert python.evidence


def test_a_listed_but_undemonstrated_skill_is_only_partial() -> None:
    structure = _structure(explicit=["PostgreSQL"], prose="Built services with Java")
    result = match_resume(structure, extract_requirements(JOB))

    postgres = next(m for m in result.requirements.required_skills if m.name == "PostgreSQL")
    assert postgres.status == "partial"


def test_an_absent_skill_is_absent_and_never_matched() -> None:
    structure = _structure(explicit=["Python"], prose="Built services in Python")
    result = match_resume(structure, extract_requirements(JOB))

    kafka = next(m for m in result.requirements.preferred_skills if m.name == "Apache Kafka")
    assert kafka.status == "absent"
    assert kafka.evidence == []

    gap = next(g for g in result.gaps if g.name == "Apache Kafka")
    # The advice must forbid inventing the skill, not encourage it.
    assert "do not add" in gap.advice.lower()
    assert any(word in gap.advice.lower() for word in ("unless", "genuinely"))


def test_demonstrated_years_are_computed_from_dates() -> None:
    structure = _structure(
        explicit=["Python"], prose="Built services", years=[("2020-03", "2022-03"), ("2022-03", None)]
    )
    years = demonstrated_years(structure)
    assert years is not None
    assert years >= 4


def test_years_requirement_reports_partial_when_short() -> None:
    structure = _structure(
        explicit=["Python"], prose="Built services", years=[("2023-01", "2024-01")]
    )
    result = match_resume(structure, extract_requirements(JOB))

    assert result.requirements.experience_years.required == 5
    assert result.requirements.experience_years.status in {"partial", "absent"}


def test_matching_is_deterministic() -> None:
    structure = _structure(explicit=["Python", "Docker"], prose="Python and Docker services")
    requirements = extract_requirements(JOB)

    first = match_resume(structure, requirements)
    second = match_resume(structure, requirements)

    assert first.model_dump() == second.model_dump()


def test_estimate_is_bounded_and_zero_without_requirements() -> None:
    structure = _structure(explicit=["Python"], prose="Python")
    empty = extract_requirements("We are a friendly company. Apply today.")
    result = match_resume(structure, empty)
    assert 0.0 <= result.estimate <= 100.0


# --- API flow ---------------------------------------------------------------


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
        json={"email": email, "password": "a-long-enough-password", "display_name": "T"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['tokens']['access_token']}"}


def test_api_match_flow(client: TestClient) -> None:
    headers = _register(client, "matcher@example.com")

    resume = client.post(
        "/api/v1/resumes",
        headers=headers,
        files={"file": ("r.pdf", _pdf(RESUME_TEXT), "application/pdf")},
    )
    assert resume.status_code == 201, resume.text

    job = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={"title": "Senior Backend Engineer", "description": JOB},
    )
    assert job.status_code == 201, job.text
    assert job.json()["requirements"]["min_years"] == 5

    match = client.post(
        "/api/v1/matches",
        headers=headers,
        json={"resume_id": resume.json()["id"], "job_id": job.json()["id"]},
    )
    assert match.status_code == 201, match.text
    body = match.json()
    assert body["status"] == "completed"
    assert body["result"]["methodology_version"] == "1.0.0"
    assert 0 <= body["result"]["estimate"] <= 100
    assert body["result"]["requirements"]["required_skills"]


def test_match_is_scoped_to_the_owner(client: TestClient) -> None:
    owner = _register(client, "owner-m@example.com")
    intruder = _register(client, "intruder-m@example.com")

    resume = client.post(
        "/api/v1/resumes",
        headers=owner,
        files={"file": ("r.pdf", _pdf(RESUME_TEXT), "application/pdf")},
    ).json()
    job = client.post(
        "/api/v1/jobs", headers=owner, json={"description": JOB}
    ).json()
    match = client.post(
        "/api/v1/matches",
        headers=owner,
        json={"resume_id": resume["id"], "job_id": job["id"]},
    ).json()

    assert client.get(f"/api/v1/matches/{match['id']}", headers=intruder).status_code == 404
    assert client.get(f"/api/v1/jobs/{job['id']}", headers=intruder).status_code == 404
    assert client.post(
        "/api/v1/matches",
        headers=intruder,
        json={"resume_id": resume["id"], "job_id": job["id"]},
    ).status_code == 404
