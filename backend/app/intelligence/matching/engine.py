"""Deterministic resume ↔ job-description matching.

The estimate is arithmetic over counted states. No provider is consulted, so the
number cannot change between two identical calls — and a keyword that appears in
an unrelated context is not counted as a match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.intelligence.taxonomy import canonicalise
from app.schemas.matching import (
    EducationRequirement,
    Gap,
    JobMatch,
    JobRequirements,
    MatchRequirements,
    ResponsibilityMatch,
    SkillMatch,
    YearsRequirement,
)
from app.schemas.resume import ResumeStructure

_STOPWORDS = {
    "the", "and", "for", "with", "you", "will", "our", "are", "that", "this",
    "have", "has", "from", "your", "who", "all", "can", "not", "but", "they",
    "their", "them", "work", "working", "team", "teams", "role", "job",
}

_DEGREE_RANK = {"bachelor": 1, "master": 2, "doctorate": 3}

# Weights renormalise over whichever inputs the description actually supplies.
_WEIGHTS = {"required": 0.60, "preferred": 0.20, "experience": 0.12, "education": 0.08}


def _months(start: str | None, end: str | None) -> int | None:
    """Duration in months, or None when either bound is unparseable."""
    def parse(value: str | None) -> tuple[int, int] | None:
        if not value:
            return None
        match = re.match(r"(\d{4})(?:-(\d{2}))?", value.strip())
        if not match:
            return None
        year = int(match.group(1))
        month = int(match.group(2) or 6)
        return year, month

    if end is None:
        end_pair = (date.today().year, date.today().month)
    else:
        end_pair = parse(end)
    start_pair = parse(start)
    if start_pair is None or end_pair is None:
        return None
    delta = (end_pair[0] - start_pair[0]) * 12 + (end_pair[1] - start_pair[1])
    return delta if delta >= 0 else None


def demonstrated_years(structure: ResumeStructure) -> float | None:
    """Sum of role durations. Overlapping roles are summed, then trimmed to the
    span between the earliest start and latest end, which is never an overcount.
    """
    durations = [
        months
        for role in structure.experience
        if (months := _months(role.start, role.end)) is not None
    ]
    if not durations:
        return None

    total = sum(durations) / 12

    # Overlapping roles would otherwise double-count. Cap the sum at the span
    # from the earliest start to the latest end (an open-ended role ends now).
    current_year = date.today().year
    starts: list[int] = []
    ends: list[int] = []
    for role in structure.experience:
        if role.start and (match := re.match(r"(\d{4})", role.start)):
            starts.append(int(match.group(1)))
            if role.end and (end_match := re.match(r"(\d{4})", role.end)):
                ends.append(int(end_match.group(1)))
            else:
                ends.append(current_year)

    if starts and ends:
        span = max(ends) - min(starts)
        if span > 0 and total > span:
            total = float(span)
    return round(total, 1)


@dataclass(frozen=True)
class _ResumeView:
    """The resume, prepared once per match.

    Every per-skill lookup used to rebuild the canonical skill sets, re-read the
    whole body and re-join every role and project. That made a match quadratic
    in the number of requirements — a 40-skill description read the resume 40
    times. Prepared once, the match is linear in requirements.
    """

    explicit: frozenset[str | None]
    inferred: frozenset[str | None]
    prose: str
    roles: tuple[str, ...]
    projects: tuple[str, ...]


def _view(structure: ResumeStructure) -> _ResumeView:
    return _ResumeView(
        explicit=frozenset(canonicalise(item) for item in structure.skills.explicit),
        inferred=frozenset(canonicalise(item.name) for item in structure.skills.inferred),
        prose=structure.substantiated_text().lower(),
        roles=tuple(
            " ".join(
                filter(None, [role.title, role.organisation, *(b.text for b in role.bullets)])
            ).lower()
            for role in structure.experience
        ),
        projects=tuple(
            " ".join(filter(None, [project.name, project.description, *(b.text for b in project.bullets)])).lower()
            for project in structure.projects
        ),
    )


def _evidence_for(skill: str, view: _ResumeView) -> list[str]:
    locations: list[str] = []
    if canonicalise(skill) in view.explicit:
        locations.append("skills.explicit")
    needle = skill.lower()
    for index, haystack in enumerate(view.roles):
        if needle in haystack:
            locations.append(f"experience[{index}]")
    for index, haystack in enumerate(view.projects):
        if needle in haystack:
            locations.append(f"projects[{index}]")
    return locations


def _match_skill(skill: str, view: _ResumeView) -> SkillMatch:
    explicit = view.explicit
    inferred = view.inferred
    prose = view.prose
    canonical = canonicalise(skill)
    evidence = _evidence_for(skill, view)

    if canonical in explicit and skill.lower() in prose:
        return SkillMatch(
            name=skill,
            status="matched",
            evidence=evidence,
            note="Claimed and demonstrated in the resume body.",
        )
    if canonical in explicit:
        return SkillMatch(
            name=skill,
            status="partial",
            evidence=evidence,
            note="Listed in the skills section but never demonstrated in a role or project.",
        )
    if canonical in inferred or skill.lower() in prose:
        return SkillMatch(
            name=skill,
            status="weakly_demonstrated",
            evidence=evidence,
            note="Appears in the resume body but is not claimed in the skills list.",
        )
    return SkillMatch(
        name=skill,
        status="absent",
        evidence=[],
        note="Not found anywhere in the resume.",
    )


def _skill_score(matches: list[SkillMatch]) -> float | None:
    if not matches:
        return None
    credit = {"matched": 1.0, "partial": 0.6, "weakly_demonstrated": 0.35, "absent": 0.0}
    return sum(credit[m.status] for m in matches) / len(matches)


def _education_match(required: str | None, structure: ResumeStructure) -> EducationRequirement:
    if not required:
        return EducationRequirement(required=None, status="not_applicable")

    present = [
        _DEGREE_RANK.get(entry.degree.lower().split()[0].strip(".,"), 0)
        for entry in structure.education
        if entry.degree
    ]
    best = max(present) if present else 0
    required_rank = _DEGREE_RANK.get(required, 1)

    if best >= required_rank:
        status = "matched"
    elif best > 0:
        status = "partial"
    elif structure.education:
        status = "partial"
    else:
        status = "absent"
    return EducationRequirement(required=required, status=status)


def _responsibility_match(lines: list[str], view: _ResumeView) -> list[ResponsibilityMatch]:
    prose_tokens = {
        token
        for token in re.findall(r"[a-z]{4,}", view.prose)
        if token not in _STOPWORDS
    }
    results: list[ResponsibilityMatch] = []
    for line in lines:
        tokens = {
            token
            for token in re.findall(r"[a-z]{4,}", line.lower())
            if token not in _STOPWORDS
        }
        if not tokens:
            continue
        overlap = len(tokens & prose_tokens) / len(tokens)
        status = "matched" if overlap >= 0.5 else "partial" if overlap >= 0.25 else "absent"
        results.append(ResponsibilityMatch(text=line, status=status))
    return results


def match_resume(structure: ResumeStructure, requirements: JobRequirements) -> JobMatch:
    view = _view(structure)
    required = [_match_skill(skill, view) for skill in requirements.required_skills]
    preferred = [_match_skill(skill, view) for skill in requirements.preferred_skills]

    demonstrated = demonstrated_years(structure)
    if requirements.min_years is None:
        years = YearsRequirement(status="not_applicable", demonstrated=demonstrated)
    elif demonstrated is None:
        years = YearsRequirement(
            required=requirements.min_years, demonstrated=None, status="absent"
        )
    elif demonstrated >= requirements.min_years:
        years = YearsRequirement(
            required=requirements.min_years, demonstrated=demonstrated, status="matched"
        )
    else:
        years = YearsRequirement(
            required=requirements.min_years, demonstrated=demonstrated, status="partial"
        )

    education = _education_match(requirements.degree_level, structure)
    responsibilities = _responsibility_match(requirements.responsibilities, view)

    contributions: list[tuple[float, float]] = []
    required_score = _skill_score(required)
    if required_score is not None:
        contributions.append((_WEIGHTS["required"], required_score))
    preferred_score = _skill_score(preferred)
    if preferred_score is not None:
        contributions.append((_WEIGHTS["preferred"], preferred_score))
    if years.status != "not_applicable":
        years_score = {"matched": 1.0, "partial": 0.5, "absent": 0.0}[years.status]
        contributions.append((_WEIGHTS["experience"], years_score))
    if education.status != "not_applicable":
        education_score = {"matched": 1.0, "partial": 0.5, "absent": 0.0}[education.status]
        contributions.append((_WEIGHTS["education"], education_score))

    total_weight = sum(weight for weight, _ in contributions)
    estimate = (
        round(100 * sum(weight * score for weight, score in contributions) / total_weight, 1)
        if total_weight
        else 0.0
    )

    gaps: list[Gap] = []
    # Missing required skills first, then missing preferred ones: a preferred
    # skill you lack is still worth knowing about, just less urgent.
    for match in [*required, *preferred]:
        if match.status == "absent":
            gaps.append(
                Gap(
                    name=match.name,
                    advice=(
                        "Not present in the resume. Do not add it unless you have genuinely used it — "
                        "an unevidenced claim is worse than a visible gap."
                    ),
                )
            )
        elif match.status in {"partial", "weakly_demonstrated"}:
            gaps.append(
                Gap(
                    name=match.name,
                    advice=(
                        "Mentioned without supporting evidence. Add a role, project or bullet where "
                        "you actually used it, or remove the claim."
                    ),
                )
            )

    summary = {
        "required_total": len(required),
        "required_matched": sum(1 for m in required if m.status == "matched"),
        "required_absent": sum(1 for m in required if m.status == "absent"),
        "preferred_total": len(preferred),
        "preferred_matched": sum(1 for m in preferred if m.status == "matched"),
    }

    return JobMatch(
        estimate=estimate,
        requirements=MatchRequirements(
            required_skills=required,
            preferred_skills=preferred,
            experience_years=years,
            education=education,
            responsibilities=responsibilities,
        ),
        gaps=gaps,
        summary=summary,
    )
