"""Resume parsing contract tests (docs/API.md §2.4).

The assertions are mostly about what the parser must *not* do: keep `None` as
`None`, keep ambiguous dates ambiguous, and never promote a mention in prose to a
claimed skill. A parser that invents plausible values would pass a "does it
produce data" test while corrupting every score built on top of it.
"""

from __future__ import annotations

from app.intelligence.parser import classify_heading, parse_document
from app.intelligence.taxonomy import canonicalise, find_skills, size
from app.schemas.resume import ExtractionResult

FULL_RESUME = """ARJUN MEHTA
arjun.mehta@example.com | +91 98765 43210 | linkedin.com/in/arjunmehta

SUMMARY
Backend engineer with four years building payment services.

TECHNICAL SKILLS
Python, Django, PostgreSQL, Docker, AWS, Kubernetes, Redis

WORK EXPERIENCE
Backend Engineer
Acme Payments | Mar 2022 - Present
• Built a ledger service handling 2M daily transactions
• Reduced p99 latency from 800ms to 220ms by adding Redis caching
• Mentored three junior engineers

Software Engineer
Northwind Systems | Jul 2020 - Feb 2022
• Automated reconciliation reports with Python and Pandas
• Wrote the first integration test suite with Pytest

EDUCATION
B.Tech in Computer Science
National Institute of Technology | 2016 - 2020

CERTIFICATIONS
AWS Certified Solutions Architect - Amazon Web Services - Mar 2023

PROJECTS
Ledger Simulator
• Simulated double-entry accounting with Python and FastAPI

ACHIEVEMENTS
• Won internal hackathon 2023
"""

STUDENT_RESUME = """PRIYA SHARMA
priya.sharma@example.com

SUMMARY
Final-year student focused on backend systems.

TECHNICAL SKILLS
Python, Java, SQL

PROJECTS
Campus Navigator
• Built a pathfinding demo with Python and FastAPI

EDUCATION
B.Sc in Computer Science
State University | 2022 - 2025
"""


def _extraction(text: str, *, method: str = "text_layer", confidence: float = 0.95) -> ExtractionResult:
    return ExtractionResult(
        text=text,
        page_count=1,
        method=method,  # type: ignore[arg-type]
        confidence=confidence,
        ocr_used=False,
        warnings=[],
    )


# --- Section headings -------------------------------------------------------


def test_headings_are_recognised() -> None:
    assert classify_heading("WORK EXPERIENCE") == "experience"
    assert classify_heading("Technical Skills:") == "skills"
    assert classify_heading("Education") == "education"
    assert classify_heading("Work Experience & Internships") == "experience"


def test_prose_beginning_with_a_heading_word_is_not_a_heading() -> None:
    """\"Experience with Python and Django\" is a sentence, not a section."""
    assert classify_heading("Experience with Python and Django") is None
    assert classify_heading("Skills that I have used extensively") is None


def test_unknown_heading_is_none() -> None:
    assert classify_heading("My Journey So Far") is None


# --- Contact ----------------------------------------------------------------


def test_contact_is_extracted() -> None:
    structure = parse_document(_extraction(FULL_RESUME))

    assert structure.contact.name == "ARJUN MEHTA"
    assert structure.contact.email == "arjun.mehta@example.com"
    assert structure.contact.phone is not None
    assert any("linkedin.com" in link for link in structure.contact.links)


def test_year_range_is_not_mistaken_for_a_phone_number() -> None:
    text = "ARJUN MEHTA\narjun@example.com\n\nWORK EXPERIENCE\nEngineer\nAcme | 2019 - 2021\n"
    structure = parse_document(_extraction(text))

    assert structure.contact.phone is None


# --- Experience -------------------------------------------------------------


def test_experience_entries_are_split_with_dates() -> None:
    structure = parse_document(_extraction(FULL_RESUME))

    assert len(structure.experience) == 2

    current, previous = structure.experience

    assert current.title == "Backend Engineer"
    assert current.organisation == "Acme Payments"
    assert current.start == "2022-03"
    assert current.end is None
    assert current.date_precision == "present"
    assert len(current.bullets) == 3

    assert previous.title == "Software Engineer"
    assert previous.organisation == "Northwind Systems"
    assert previous.start == "2020-07"
    assert previous.end == "2022-02"
    assert previous.date_precision == "month"


def test_bullets_keep_their_source_span() -> None:
    structure = parse_document(_extraction(FULL_RESUME))
    bullet = structure.experience[0].bullets[0]

    assert bullet.span is not None
    start, end = bullet.span
    assert FULL_RESUME[start:end] == bullet.text
    assert "ledger service" in bullet.text


def test_employer_is_not_borrowed_when_the_document_does_not_state_one() -> None:
    text = "ARJUN MEHTA\narjun@example.com\n\nWORK EXPERIENCE\nConsultant\n• Advised clients on delivery\n"
    structure = parse_document(_extraction(text))

    assert structure.experience[0].title == "Consultant"
    assert structure.experience[0].organisation is None
    assert any(item.reason == "dates_missing" for item in structure.uncertain)


def test_ambiguous_date_is_reported_not_guessed() -> None:
    text = (
        "ARJUN MEHTA\narjun@example.com\n\nWORK EXPERIENCE\n"
        "Backend Engineer\nAcme Systems | 03/04\n• Built things\n"
    )
    structure = parse_document(_extraction(text))

    assert structure.experience[0].start is None
    assert structure.experience[0].date_precision == "unknown"
    assert any(item.reason == "date_ambiguous" for item in structure.uncertain)


# --- Education --------------------------------------------------------------


def test_degree_and_institution_on_separate_lines_form_one_entry() -> None:
    structure = parse_document(_extraction(FULL_RESUME))

    assert len(structure.education) == 1
    entry = structure.education[0]
    assert entry.degree == "B.Tech"
    assert entry.institution == "National Institute of Technology"
    assert entry.start == "2016"
    assert entry.end == "2020"


# --- Skills -----------------------------------------------------------------


def test_explicit_skills_come_from_the_skills_section_only() -> None:
    structure = parse_document(_extraction(FULL_RESUME))

    assert "Python" in structure.skills.explicit
    assert "PostgreSQL" in structure.skills.explicit
    assert "Kubernetes" in structure.skills.explicit


def test_prose_mentions_are_inferred_not_claimed() -> None:
    structure = parse_document(_extraction(FULL_RESUME))

    explicit = {name.lower() for name in structure.skills.explicit}
    inferred = {skill.name.lower(): skill.basis for skill in structure.skills.inferred}

    assert "pandas" in inferred
    assert "pytest" in inferred
    assert "fastapi" in inferred
    # A skill already claimed in the skills section is not duplicated as inferred.
    assert "redis" not in inferred
    assert "redis" in explicit
    assert all(basis for basis in inferred.values())


def test_skills_line_written_as_a_sentence_is_recovered() -> None:
    text = "ARJUN MEHTA\narjun@example.com\n\nTECHNICAL SKILLS\nPython and Django\n"
    structure = parse_document(_extraction(text))

    assert "Python" in structure.skills.explicit
    assert "Django" in structure.skills.explicit


# --- Sections and metrics ---------------------------------------------------


def test_section_presence_reflects_the_headings() -> None:
    structure = parse_document(_extraction(FULL_RESUME))
    sections = structure.sections

    assert sections.summary is True
    assert sections.experience is True
    assert sections.education is True
    assert sections.skills is True
    assert sections.projects is True
    assert sections.certifications is True
    assert sections.achievements is True
    assert sections.leadership is False


def test_candidate_without_work_history_has_no_experience_section() -> None:
    """The fresher case: scoring must see `not applicable`, not a zero score."""
    structure = parse_document(_extraction(STUDENT_RESUME))

    assert structure.sections.experience is False
    assert structure.experience == []
    assert structure.sections.projects is True
    assert len(structure.projects) == 1
    assert "Python" in structure.skills.explicit


def test_full_resume_produces_no_spurious_uncertainty() -> None:
    structure = parse_document(_extraction(FULL_RESUME))

    assert structure.uncertain == []


def test_metrics_are_computed_from_the_document() -> None:
    structure = parse_document(_extraction(FULL_RESUME))

    assert structure.word_count > 50
    assert structure.bullet_count == 6  # 3 + 2 experience, 1 project
    assert structure.has_dates is True
    assert "month" in structure.date_formats
    assert structure.page_count == 1


def test_low_confidence_extraction_raises_layout_risk() -> None:
    low_quality = FullExtraction = _extraction(FULL_RESUME, method="partial", confidence=0.4)
    structure = parse_document(FullExtraction)

    assert structure.reading_order_risk == "medium"
    assert low_quality.method == "partial"


def test_empty_document_yields_empty_structure_without_exceptions() -> None:
    structure = parse_document(_extraction("", method="failed", confidence=0.0))

    assert structure.experience == []
    assert structure.skills.explicit == []
    assert structure.sections.experience is False
    assert structure.reading_order_risk == "high"


# --- Taxonomy ---------------------------------------------------------------


def test_taxonomy_has_real_coverage() -> None:
    assert size() >= 120


def test_aliases_resolve_to_canonical_names() -> None:
    assert canonicalise("JS") == "JavaScript"
    assert canonicalise("postgres") == "PostgreSQL"
    assert canonicalise("k8s") == "Kubernetes"


def test_unknown_term_is_not_promoted_to_a_skill() -> None:
    assert canonicalise("Zorblatt Engineering") is None


def test_longest_alias_wins() -> None:
    assert find_skills("Built with React Native") == ["React Native"]


def test_ambiguous_words_need_an_explicit_skills_context() -> None:
    assert find_skills("Go the extra mile and be swift") == []
    assert "Go" in find_skills("Go, Rust", include_ambiguous=True)
