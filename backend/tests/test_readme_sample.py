"""Pin the sample published in README §03 and §07.

The input is rendered to a PDF and sent through the real extraction, parsing,
scoring and matching path. If a rule change moves the published number, this
test fails instead of letting the README drift away from the engine.

The source text mirrors `scripts/readme_metrics.py`; keep the two in sync. The
clock is frozen to the measurement date so the documented result does not decay
because a calendar year rolled over.
"""

from __future__ import annotations

import io
from datetime import date, datetime, timezone

import pymupdf
import pytest

from app.document.extraction import extract
from app.intelligence.matching import engine as matching_module
from app.intelligence.matching.engine import match_resume
from app.intelligence.matching.requirements import extract_requirements
from app.intelligence.parser import parse_document
from app.intelligence.scoring import skills as skills_module
from app.intelligence.scoring import structure as structure_module
from app.intelligence.scoring.engine import score_resume

RESUME = """ARJUN MEHTA
arjun.mehta@example.com | +91 98765 43210 | linkedin.com/in/arjunmehta

SUMMARY
Backend engineer with four years building payment services.

TECHNICAL SKILLS
Python, Django, PostgreSQL, Docker, AWS, Kubernetes, Redis

WORK EXPERIENCE
Backend Engineer
Acme Payments | Mar 2022 - Present
- Built a ledger service handling 2M daily transactions
- Worked on latency improvements
- Responsible for mentoring

Software Engineer
Northwind Systems | Jul 2020 - Feb 2022
- Automated reconciliation reports with Python and Pandas

EDUCATION
B.Tech in Computer Science
National Institute of Technology | 2016 - 2020
"""

JOB = """Senior Backend Engineer
Requirements:
We need 5+ years of Python experience, PostgreSQL, Kubernetes and Terraform.
Nice to have: Kafka, GraphQL.
Responsibilities:
Own the payment ledger service and mentor engineers.
Bachelor's degree in Computer Science required.
"""


def _sample_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(40, 40, 555, 800), RESUME, fontsize=9)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


@pytest.fixture
def frozen_measurement_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 7, tzinfo=tz or timezone.utc)

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 7)

    monkeypatch.setattr(skills_module, "datetime", FixedDateTime)
    monkeypatch.setattr(structure_module, "datetime", FixedDateTime)
    monkeypatch.setattr(matching_module, "date", FixedDate)


def test_published_sample_score_is_pinned(frozen_measurement_clock: None) -> None:
    extraction = extract(_sample_pdf(), "application/pdf")
    structure = parse_document(extraction)
    result = score_resume(structure, extraction_confidence=extraction.confidence)

    assert extraction.method == "text_layer"
    assert extraction.confidence == 1.0
    assert structure.word_count == 87
    assert len(structure.experience) == 2
    assert structure.bullet_count == 4
    assert len(structure.skills.explicit) == 7

    assert result.bundle.overall == 82.6
    assert result.bundle.band == "strong"
    assert result.ats.estimate == 88.2
    assert {name: component.value for name, component in result.bundle.components.items()} == {
        "content_quality": 78.4,
        "experience": 86.9,
        "skills": 66.2,
        "structure": 100.0,
        "ats_compatibility": 88.2,
        "language_readability": 74.5,
    }


def test_published_sample_findings_reconcile(frozen_measurement_clock: None) -> None:
    extraction = extract(_sample_pdf(), "application/pdf")
    result = score_resume(parse_document(extraction), extraction_confidence=extraction.confidence)

    assert len(result.findings) == 13
    severities = ("critical", "high", "medium", "low", "info")
    assert {level: sum(f.severity == level for f in result.findings) for level in severities} == {
        "critical": 0,
        "high": 2,
        "medium": 6,
        "low": 5,
        "info": 0,
    }

    impacts = [finding.score_impact or 0.0 for finding in result.findings]
    assert impacts == sorted(impacts, reverse=True)
    assert sum(impacts) == pytest.approx(100.0 - result.bundle.overall, abs=0.15)

    assert [(finding.criterion, finding.score_impact) for finding in result.findings[:5]] == [
        ("CQ-03", 3.12),
        ("SK-04", 2.98),
        ("AT-04", 1.76),
        ("SK-05", 1.71),
        ("EX-05", 1.43),
    ]


def test_published_sample_match_is_pinned(frozen_measurement_clock: None) -> None:
    extraction = extract(_sample_pdf(), "application/pdf")
    structure = parse_document(extraction)
    match = match_resume(structure, extract_requirements(JOB))

    assert match.estimate == 49.0
    assert {item.name: item.status for item in match.requirements.required_skills} == {
        "Python": "matched",
        "PostgreSQL": "partial",
        "Kubernetes": "partial",
        "Terraform": "absent",
    }
    assert {item.name: item.status for item in match.requirements.preferred_skills} == {
        "Apache Kafka": "absent",
        "GraphQL": "absent",
    }
