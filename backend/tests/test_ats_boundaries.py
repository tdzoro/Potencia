"""ATS scoring boundaries, edge cases, and mathematical reconciliation tests.

Validates:
- Score bounds [0, 100] across all components and overall score.
- Score reconciliation: sum(score_impact) == 100 - overall score.
- Robustness on empty, single-word, and extreme-size resumes.
- Deterministic invariance under repeated evaluation.
- Job matching score boundaries under degenerate inputs (empty, disjoint, exact match).
"""

from __future__ import annotations

import math
import pytest

from app.intelligence.matching.engine import match_resume
from app.intelligence.matching.requirements import extract_requirements
from app.intelligence.scoring.aggregate import SPECS
from app.intelligence.scoring.engine import score_resume
from app.schemas.resume import (
    Bullet,
    Contact,
    EducationEntry,
    ExperienceEntry,
    ResumeStructure,
    SectionPresence,
    SkillSet,
    SummaryBlock,
)


def _bullets(*texts: str) -> list[Bullet]:
    return [Bullet(text=t) for t in texts]


def empty_resume() -> ResumeStructure:
    return ResumeStructure(
        contact=Contact(),
        summary=SummaryBlock(present=False, text=""),
        experience=[],
        education=[],
        skills=SkillSet(explicit=[]),
        sections=SectionPresence(
            contact=False,
            summary=False,
            experience=False,
            education=False,
            skills=False,
        ),
        word_count=0,
        bullet_count=0,
        page_count=0,
        has_dates=False,
        date_formats=[],
        reading_order_risk="none",
    )


def single_word_resume() -> ResumeStructure:
    return ResumeStructure(
        contact=Contact(name="Dev"),
        summary=SummaryBlock(present=False, text=""),
        experience=[],
        education=[],
        skills=SkillSet(explicit=[]),
        sections=SectionPresence(
            contact=True,
            summary=False,
            experience=False,
            education=False,
            skills=False,
        ),
        word_count=1,
        bullet_count=0,
        page_count=1,
        has_dates=False,
        date_formats=[],
        reading_order_risk="none",
    )


def extreme_oversized_resume() -> ResumeStructure:
    # 50 roles, each with 5 bullets of 30 words, 100 skills, 10 pages
    roles = [
        ExperienceEntry(
            title=f"Principal Engineer {i}",
            organisation=f"Enterprise {i}",
            start="2010-01",
            end="2020-01",
            date_precision="month",
            bullets=_bullets(
                *(f"Developed scalable distributed system number {j} handling heavy throughput" for j in range(5))
            ),
        )
        for i in range(50)
    ]
    skills = [f"Skill_{k}" for k in range(100)] + ["Python", "Docker", "PostgreSQL", "AWS", "Kubernetes"]
    return ResumeStructure(
        contact=Contact(
            name="Senior Architect",
            email="architect@example.com",
            phone="+1 555 9999",
            links=["https://linkedin.com/in/architect"],
        ),
        summary=SummaryBlock(
            present=True,
            text="High performing systems architect with 25 years of experience leading massive enterprise migrations.",
        ),
        experience=roles,
        education=[
            EducationEntry(
                institution="Tech University",
                degree="Ph.D.",
                field="Computer Science",
                start="2000-09",
                end="2005-06",
            )
        ],
        skills=SkillSet(explicit=skills),
        sections=SectionPresence(
            contact=True,
            summary=True,
            experience=True,
            education=True,
            skills=True,
        ),
        word_count=12000,
        bullet_count=250,
        page_count=12,
        has_dates=True,
        date_formats=["2010-01", "2020-01"],
        reading_order_risk="none",
    )


def test_empty_resume_score_boundaries_and_reconciliation() -> None:
    res = score_resume(empty_resume(), extraction_confidence=0.8)

    # 1. Overall bound
    assert 0.0 <= res.bundle.overall <= 100.0
    assert not math.isnan(res.bundle.overall)

    # 2. Components bound
    for comp_name, comp in res.bundle.components.items():
        assert 0.0 <= comp.value <= 100.0, f"Component {comp_name} out of bounds: {comp.value}"
        assert not math.isnan(comp.value)

    # 3. Mathematical reconciliation
    impact = sum(f.score_impact or 0.0 for f in res.findings)
    assert impact == pytest.approx(100.0 - res.bundle.overall, abs=0.1)

    # 4. Finding integrity
    assert len(res.findings) > 0
    for finding in res.findings:
        assert finding.id
        assert finding.title.strip()
        assert finding.explanation.strip()
        assert finding.remediation.strip()
        assert finding.severity in ("critical", "high", "medium", "low", "info")


def test_single_word_resume_boundaries() -> None:
    res = score_resume(single_word_resume(), extraction_confidence=0.9)
    assert 0.0 <= res.bundle.overall <= 100.0
    for comp in res.bundle.components.values():
        assert 0.0 <= comp.value <= 100.0

    impact = sum(f.score_impact or 0.0 for f in res.findings)
    assert impact == pytest.approx(100.0 - res.bundle.overall, abs=0.1)


def test_extreme_oversized_resume_boundaries() -> None:
    res = score_resume(extreme_oversized_resume(), extraction_confidence=0.95)
    assert 0.0 <= res.bundle.overall <= 100.0
    for comp in res.bundle.components.values():
        assert 0.0 <= comp.value <= 100.0

    impact = sum(f.score_impact or 0.0 for f in res.findings)
    assert impact == pytest.approx(100.0 - res.bundle.overall, abs=0.1)


def test_scoring_determinism_across_iterations() -> None:
    resume = extreme_oversized_resume()
    baseline = score_resume(resume, extraction_confidence=0.95)

    for _ in range(5):
        run = score_resume(resume, extraction_confidence=0.95)
        assert run.bundle.overall == baseline.bundle.overall
        assert [f.id for f in run.findings] == [f.id for f in baseline.findings]
        assert [f.score_impact for f in run.findings] == [f.score_impact for f in baseline.findings]


def test_matching_score_boundaries_on_degenerate_inputs() -> None:
    resume = extreme_oversized_resume()

    # Degenerate 1: Empty job description
    req_empty = extract_requirements("")
    match_empty = match_resume(resume, req_empty)
    assert 0.0 <= match_empty.estimate <= 100.0

    # Degenerate 2: Completely disjoint job description (Game Developer)
    disjoint_job = """Senior Game Developer
    Requirements:
    - 10+ years experience
    - Unity, Unreal Engine, C++, C#, Blender
    """
    req_disjoint = extract_requirements(disjoint_job)
    match_disjoint = match_resume(resume, req_disjoint)
    assert 0.0 <= match_disjoint.estimate <= 100.0

    # Degenerate 3: Exact match job description
    exact_job = """Senior Distributed Systems Architect
    Requirements:
    - Python, Docker, PostgreSQL, AWS, Kubernetes
    - Scalable distributed systems
    - Ph.D. or Master's degree in Computer Science
    - 10+ years experience
    """
    req_exact = extract_requirements(exact_job)
    match_exact = match_resume(resume, req_exact)
    assert 0.0 <= match_exact.estimate <= 100.0
    assert match_exact.estimate >= match_disjoint.estimate
