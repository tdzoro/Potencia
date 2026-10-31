"""Scoring engine entry point.

Order matters: the ATS analyzer runs first because its five checks *are* the
`ats_compatibility` category — they are scored once and reported once, never
computed twice with two different answers.

No provider, SDK or network call appears anywhere in this package. A score that
could change when an external service is unavailable would not be a score.
"""

from __future__ import annotations

from app.intelligence.ats.analyzer import analyze_ats
from app.intelligence.scoring import content, experience, language, skills
from app.intelligence.scoring import structure as structure_rules
from app.intelligence.scoring.aggregate import ScoreResult, assemble
from app.schemas.resume import ResumeStructure


def score_resume(
    structure: ResumeStructure,
    extraction_confidence: float = 0.9,
) -> ScoreResult:
    """Score a parsed resume deterministically.

    `extraction_confidence` comes from the document layer; it lowers the
    reported confidence of every category and caps the ATS estimate, so a badly
    extracted document can never present as a clean one.
    """
    ats_report, ats_criteria = analyze_ats(structure, extraction_confidence)

    categories = {
        "content_quality": content.evaluate(structure),
        "experience": experience.evaluate(structure),
        "skills": skills.evaluate(structure),
        "structure": structure_rules.evaluate(structure),
        "ats_compatibility": ats_criteria,
        "language_readability": language.evaluate(structure),
    }

    result = assemble(categories, extraction_confidence)
    result.ats = ats_report
    return result


__all__ = ["score_resume", "ScoreResult"]
