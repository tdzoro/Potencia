"""Efficiency guardrails.

The bounds here are deliberately loose — an order of magnitude above the
observed cost. They are not a benchmark; they exist to catch a return to the two
shapes the profiler found: re-sorting the heading table for every line, and
re-reading the whole resume for every required skill. Both regressions are 5–10x
slower, so a generous ceiling still catches them on a slow runner without
failing on scheduling noise.
"""

from __future__ import annotations

import time

from app.intelligence.matching.engine import match_resume
from app.intelligence.matching.requirements import extract_requirements
from app.intelligence.parser import _HEADING_PREFIXES, classify_heading, parse_document
from app.intelligence.taxonomy import _normalise_key, all_canonical_names
from app.schemas.resume import ExtractionResult, ResumeStructure

RESUME = """RITIKA SHARMA
ritika.sharma@example.com | +91 90000 11111

SUMMARY
Backend engineer with five years building payment and ledger services.

TECHNICAL SKILLS
Python, Django, PostgreSQL, Docker, AWS, Kubernetes, Redis, Kafka, Terraform, Go

WORK EXPERIENCE
Senior Backend Engineer
Acme Payments | Mar 2021 - Present
- Built a ledger service handling 2M daily transactions in Python
- Reduced p99 latency from 800ms to 220ms by adding Redis caching
- Led migration of 14 services to Kubernetes with Terraform

Backend Engineer
Northwind Systems | Jul 2018 - Feb 2021
- Automated reconciliation with Python and PostgreSQL
- Shipped a Docker-based deployment pipeline

EDUCATION
B.Tech in Computer Science
National Institute of Technology | 2014 - 2018
"""


def _extraction(text: str) -> ExtractionResult:
    return ExtractionResult(
        text=text,
        page_count=1,
        method="text_layer",
        confidence=0.95,
        ocr_used=False,
        warnings=[],
    )


def _structure() -> ResumeStructure:
    return parse_document(_extraction(RESUME))


def _requirements(count: int):
    skills = all_canonical_names()[:count]
    return extract_requirements(
        "Senior Backend Engineer\nRequirements:\n"
        f"We need 5+ years of experience with {', '.join(skills)}.\n"
        "Bachelor's degree in Computer Science required.\n"
    )


def test_heading_keywords_are_ordered_once_at_import() -> None:
    """The table is sorted by length at import, longest first.

    Longest-first is not cosmetic: it is what makes \"React Native\" resolve
    before \"React\". Sorting per call wasted the ordering *and* the time.
    """
    assert isinstance(_HEADING_PREFIXES, tuple)
    lengths = [len(keyword) for keyword, _ in _HEADING_PREFIXES]
    assert lengths == sorted(lengths, reverse=True)


def test_classifying_many_lines_stays_cheap() -> None:
    lines = [
        "WORK EXPERIENCE",
        "Professional Summary",
        "CORE COMPETENCIES",
        "Experience with Python and Django",
        "Education and Training",
        "Projects",
        "Random prose line that is not a heading",
    ]
    budget_ms = 500.0
    started = time.perf_counter()
    for _ in range(200):
        for line in lines:
            classify_heading(line)
    elapsed_ms = (time.perf_counter() - started) * 1000

    # 1,400 classifications. Re-sorting ninety keywords per line ran several
    # times over this budget.
    assert elapsed_ms < budget_ms, f"1,400 classifications took {elapsed_ms:.1f} ms"


def test_matching_prepares_the_resume_once(monkeypatch) -> None:
    """One read of the document per match, not one per requirement."""
    structure = _structure()
    calls = {"count": 0}
    original = ResumeStructure.substantiated_text

    def counting(self: ResumeStructure) -> str:
        calls["count"] += 1
        return original(self)

    monkeypatch.setattr(ResumeStructure, "substantiated_text", counting)

    result = match_resume(structure, _requirements(40))

    assert result.estimate >= 0.0
    assert calls["count"] == 1


def test_matching_forty_requirements_stays_within_budget() -> None:
    structure = _structure()
    requirements = _requirements(40)
    runs = 10
    started = time.perf_counter()
    for _ in range(runs):
        match_resume(structure, requirements)
    per_match_ms = (time.perf_counter() - started) * 1000 / runs

    assert per_match_ms < 250.0, f"a 40-skill match took {per_match_ms:.1f} ms"


def test_parsing_a_long_document_stays_within_budget() -> None:
    text = "\n\n".join([RESUME] * 8)
    started = time.perf_counter()
    parse_document(_extraction(text))
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert elapsed_ms < 500.0, f"parsing eight documents of text took {elapsed_ms:.1f} ms"


def test_skill_normalisation_is_cached() -> None:
    subject = "postgresql-cache-probe"
    _normalise_key(subject)
    before = _normalise_key.cache_info().hits
    _normalise_key(subject)

    assert _normalise_key.cache_info().hits == before + 1
