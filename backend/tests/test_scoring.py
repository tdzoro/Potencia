"""Scoring engine contract tests (docs/SCORING_METHODOLOGY.md).

These construct `ResumeStructure` directly rather than depending on the parser:
the scoring engine's contract is the *structure*, and a parser change must not
silently change what these tests are asserting.
"""

from __future__ import annotations

import re

import pytest

from app.intelligence.scoring.aggregate import SPECS, band_for
from app.intelligence.scoring.engine import score_resume
from app.intelligence.taxonomy import contains_skill
from app.schemas.resume import (
    Bullet,
    Contact,
    EducationEntry,
    ExperienceEntry,
    ProjectEntry,
    ResumeStructure,
    SectionPresence,
    SkillSet,
    SummaryBlock,
)
from app.schemas.scores import CATEGORY_WEIGHTS


def bullets(*texts: str) -> list[Bullet]:
    return [Bullet(text=text) for text in texts]


def strong_resume() -> ResumeStructure:
    return ResumeStructure(
        contact=Contact(
            name="A Candidate",
            email="candidate@example.com",
            phone="+1 555 0100",
            links=["linkedin.com/in/candidate"],
        ),
        summary=SummaryBlock(
            present=True,
            text=(
                "Backend engineer working on billing and payments infrastructure. "
                "Reduced reconciliation time across four services while leading a team "
                "of five engineers through a platform migration."
            ),
        ),
        experience=[
            ExperienceEntry(
                title="Senior Engineer",
                organisation="Acme",
                start="2021-01",
                end=None,
                date_precision="present",
                bullets=bullets(
                    "Deliver the billing platform that processes 40,000 requests per day in Python",
                    "Lead a team of 5 engineers across two time zones",
                    "Scale the ingestion pipeline to 2 million events per hour on Kubernetes",
                    "Reduce reconciliation time from 3 hours to 20 minutes using PostgreSQL",
                    "Own the on-call rotation for 12 services running on AWS",
                ),
            ),
            ExperienceEntry(
                title="Engineer",
                organisation="Beta",
                start="2018-03",
                end="2020-12",
                date_precision="month",
                bullets=bullets(
                    "Migrated 14 services from a monolith to containerised deployments with Docker",
                    "Reduced page load time by 45 percent across the customer portal",
                    "Built a reporting service in FastAPI used by 300 analysts weekly",
                    "Automated weekly releases, removing 6 hours of manual work",
                    "Improved search relevance with Redis caching, lifting click-through by 18 percent",
                ),
            ),
        ],
        education=[
            EducationEntry(
                institution="Example Institute",
                degree="B.Tech",
                field="Computer Science",
                start="2014-08",
                end="2018-05",
            )
        ],
        skills=SkillSet(
            explicit=[
                "Python",
                "PostgreSQL",
                "Docker",
                "Kubernetes",
                "FastAPI",
                "Redis",
                "AWS",
                "React",
                "TypeScript",
                "Git",
            ]
        ),
        sections=SectionPresence(
            contact=True,
            summary=True,
            experience=True,
            education=True,
            skills=True,
        ),
        word_count=320,
        bullet_count=10,
        page_count=1,
        has_dates=True,
        date_formats=["2024-03"],
        reading_order_risk="none",
    )


def weak_resume() -> ResumeStructure:
    return ResumeStructure(
        contact=Contact(name="A Candidate", email="candidate@example.com"),
        summary=SummaryBlock(
            present=True,
            text="Hard working team player looking for opportunities. I am passionate about various tasks.",
        ),
        experience=[
            ExperienceEntry(
                title="Engineer",
                organisation="Acme",
                start="2021-01",
                end=None,
                date_precision="present",
                bullets=bullets(
                    "Worked on the backend",
                    "Helped the team with things",
                    "Responsible for various tasks",
                    "Involved in the project",
                ),
            )
        ],
        education=[],
        skills=SkillSet(explicit=["Python", "python", "JS", "JavaScript"]),
        sections=SectionPresence(contact=True, summary=True, experience=True, skills=True),
        word_count=120,
        bullet_count=4,
        page_count=1,
        has_dates=True,
        date_formats=["Jan 2021"],
        reading_order_risk="none",
    )


def no_experience_resume() -> ResumeStructure:
    """A first-time candidate: education and projects, no work history at all."""
    return ResumeStructure(
        contact=Contact(name="A Student", email="student@example.com"),
        summary=SummaryBlock(
            present=True,
            text="Computer science student focused on distributed systems and backend development.",
        ),
        education=[
            EducationEntry(
                institution="Example Institute",
                degree="B.Tech",
                field="Computer Science",
                start="2023-08",
                end="2027-05",
            )
        ],
        skills=SkillSet(explicit=["Python", "C++", "Git"]),
        sections=SectionPresence(
            contact=True, summary=True, education=True, skills=True, experience=False
        ),
        word_count=80,
        bullet_count=0,
        page_count=1,
        has_dates=True,
        date_formats=["2024-03"],
        reading_order_risk="none",
    )


# --- Structure of the result -------------------------------------------------


def test_complete_resume_scores_all_six_categories() -> None:
    result = score_resume(strong_resume(), extraction_confidence=0.95)

    assert set(result.bundle.components) == set(CATEGORY_WEIGHTS)
    assert result.bundle.applicable_weight == 100
    assert 0.0 <= result.bundle.overall <= 100.0
    assert result.bundle.methodology_version == "1.1.0"
    assert result.ats is not None


def test_missing_experience_leaves_the_denominator() -> None:
    result = score_resume(no_experience_resume(), extraction_confidence=0.95)

    assert "experience" not in result.bundle.components
    assert result.bundle.applicable_weight == 80


def test_category_criteria_weights_sum_to_one_hundred() -> None:
    for category in CATEGORY_WEIGHTS:
        total = sum(spec.weight for spec in SPECS if spec.category == category)
        assert total == 100, category


def test_property_ownership_is_unique() -> None:
    properties = [spec.property for spec in SPECS]
    assert len(properties) == len(set(properties))
    assert len(SPECS) == 30


# --- Determinism -------------------------------------------------------------


def test_identical_input_produces_identical_output() -> None:
    first = score_resume(strong_resume(), extraction_confidence=0.95)
    second = score_resume(strong_resume(), extraction_confidence=0.95)

    assert first.bundle.model_dump() == second.bundle.model_dump()
    assert [f.model_dump() for f in first.findings] == [f.model_dump() for f in second.findings]


def test_weak_resume_scores_lower_than_strong_resume() -> None:
    strong = score_resume(strong_resume(), extraction_confidence=0.95)
    weak = score_resume(weak_resume(), extraction_confidence=0.95)

    assert weak.bundle.overall < strong.bundle.overall


# --- Explainability ----------------------------------------------------------


def test_findings_reconcile_with_the_overall_score() -> None:
    result = score_resume(strong_resume(), extraction_confidence=0.95)
    impact = sum(f.score_impact or 0.0 for f in result.findings)

    assert impact == pytest.approx(100.0 - result.bundle.overall, abs=0.1)


def test_weak_resume_findings_also_reconcile() -> None:
    result = score_resume(weak_resume(), extraction_confidence=0.95)
    impact = sum(f.score_impact or 0.0 for f in result.findings)

    assert impact == pytest.approx(100.0 - result.bundle.overall, abs=0.1)


def test_findings_are_ordered_by_reported_point_impact() -> None:
    result = score_resume(weak_resume(), extraction_confidence=0.95)
    impacts = [f.score_impact or 0.0 for f in result.findings]

    assert impacts == sorted(impacts, reverse=True)


def test_short_skill_requires_a_whole_mention() -> None:
    assert not contains_skill("Worked on reports and reviewed results", "R")
    assert contains_skill("Built reports with R and PostgreSQL", "R")
    assert contains_skill("Built reports with JavaScript", "JS")


def test_short_skill_is_not_substantiated_by_substring() -> None:
    resume = ResumeStructure(
        experience=[
            ExperienceEntry(
                title="Engineer",
                organisation="Acme",
                start="2024-01",
                end=None,
                bullets=bullets("Worked on reports and reviewed results"),
            )
        ],
        skills=SkillSet(explicit=["R"]),
        sections=SectionPresence(experience=True, skills=True),
    )

    result = score_resume(resume, extraction_confidence=0.95)
    criteria = {criterion.criterion: criterion for criterion in result.criteria}

    assert criteria["SK-04"].subscore == 0.0
    assert criteria["EX-05"].subscore == 0.0
    assert criteria["SK-05"].subscore == 0.0


def test_a_summary_mention_is_still_only_a_claim() -> None:
    resume = ResumeStructure(
        summary=SummaryBlock(
            present=True,
            text="Engineer with deep Kubernetes experience across production platforms.",
        ),
        experience=[
            ExperienceEntry(
                title="Engineer",
                organisation="Acme",
                start="2024-01",
                end=None,
                bullets=bullets("Delivered the billing service used by 300 customers"),
            )
        ],
        skills=SkillSet(explicit=["Kubernetes"]),
        sections=SectionPresence(summary=True, experience=True, skills=True),
    )

    result = score_resume(resume, extraction_confidence=0.95)
    criteria = {criterion.criterion: criterion for criterion in result.criteria}

    assert criteria["SK-04"].subscore == 0.0
    assert criteria["EX-05"].subscore == 0.0


def test_project_technologies_substantiate_a_skill() -> None:
    resume = ResumeStructure(
        experience=[
            ExperienceEntry(
                title="Engineer",
                organisation="Acme",
                start="2024-01",
                end=None,
                bullets=bullets("Delivered the billing service used by 300 customers"),
            )
        ],
        projects=[ProjectEntry(name="Ledger", technologies=["Kubernetes"])],
        skills=SkillSet(explicit=["Kubernetes"]),
        sections=SectionPresence(experience=True, skills=True, projects=True),
    )

    result = score_resume(resume, extraction_confidence=0.95)
    criteria = {criterion.criterion: criterion for criterion in result.criteria}

    assert criteria["SK-04"].subscore == 1.0
    assert criteria["EX-05"].subscore == 0.0


def test_unparseable_end_date_is_not_treated_as_current() -> None:
    resume = ResumeStructure(
        experience=[
            ExperienceEntry(
                title="Engineer",
                organisation="Acme",
                start="2024-01",
                end="sometime",
                bullets=bullets("Delivered billing services in Kubernetes"),
            )
        ],
        skills=SkillSet(explicit=["Kubernetes"]),
        sections=SectionPresence(experience=True, skills=True),
    )

    result = score_resume(resume, extraction_confidence=0.95)
    criteria = {criterion.criterion: criterion for criterion in result.criteria}

    assert criteria["SK-05"].subscore == 0.0


def test_an_undated_role_cannot_establish_recency() -> None:
    resume = ResumeStructure(
        experience=[
            ExperienceEntry(
                title="Engineer",
                organisation="Acme",
                start=None,
                end=None,
                bullets=bullets("Delivered billing services in Kubernetes"),
            )
        ],
        skills=SkillSet(explicit=["Kubernetes"]),
        sections=SectionPresence(experience=True, skills=True),
    )

    result = score_resume(resume, extraction_confidence=0.95)
    criteria = {criterion.criterion: criterion for criterion in result.criteria}

    assert "SK-05" not in criteria
    assert not any(finding.criterion == "SK-05" for finding in result.findings)


def test_a_blank_skill_does_not_create_a_relevance_deduction() -> None:
    resume = ResumeStructure(
        experience=[
            ExperienceEntry(
                title="Engineer",
                organisation="Acme",
                start="2024-01",
                end=None,
                bullets=bullets("Delivered billing services in Kubernetes"),
            )
        ],
        skills=SkillSet(explicit=[""]),
        sections=SectionPresence(experience=True, skills=True),
    )

    result = score_resume(resume, extraction_confidence=0.95)
    criteria = {criterion.criterion: criterion for criterion in result.criteria}

    assert "EX-05" not in criteria
    assert not any(finding.criterion == "EX-05" for finding in result.findings)


def test_every_finding_has_evidence_and_an_explanation() -> None:
    for resume in (strong_resume(), weak_resume(), no_experience_resume()):
        result = score_resume(resume, extraction_confidence=0.95)
        for finding in result.findings:
            assert finding.evidence, finding.criterion
            assert finding.explanation.strip()
            assert finding.remediation.strip()
            assert finding.title.strip()


def test_no_finding_proposes_a_fabricated_metric() -> None:
    """Remediation may ask for a number; it must never supply one."""
    fabricated = re.compile(r"\d+\s*%")

    for resume in (strong_resume(), weak_resume(), no_experience_resume()):
        result = score_resume(resume, extraction_confidence=0.95)
        for finding in result.findings:
            assert not fabricated.search(finding.remediation), finding.criterion


def test_unexplained_deduction_is_refused() -> None:
    """A criterion below 1.0 with no finding must raise, not report silently."""
    from app.intelligence.scoring.aggregate import assemble, make_result

    criteria = {
        "content_quality": [make_result("CQ-01", 0.5, detail="no finding attached")],
    }
    with pytest.raises(ValueError, match="no finding"):
        assemble(criteria, 0.95)


# --- Confidence and bands ----------------------------------------------------


def test_confidence_falls_with_extraction_quality() -> None:
    clean = score_resume(strong_resume(), extraction_confidence=0.95)
    murky = score_resume(strong_resume(), extraction_confidence=0.40)

    assert all(component.confidence == "high" for component in clean.bundle.components.values())
    assert any(component.confidence == "low" for component in murky.bundle.components.values())


def test_exceptional_band_requires_quantification_and_verifiable_skills() -> None:
    assert band_for(95.0, cq03=0.9, sk04=0.9) == "exceptional"
    assert band_for(95.0, cq03=0.5, sk04=0.9) == "strong"
    assert band_for(65.0, cq03=0.9, sk04=0.9) == "competent"
    assert band_for(45.0, cq03=0.1, sk04=0.1) == "developing"
