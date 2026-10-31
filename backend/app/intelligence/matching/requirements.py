"""Extract what a job description actually asks for.

The description is untrusted text. Nothing here executes it, and nothing is
promoted to a "required skill" unless the text says so or the skill appears
inside a section that is explicitly about requirements.
"""

from __future__ import annotations

import re

from app.intelligence.taxonomy import find_skills
from app.schemas.matching import JobRequirements

_REQUIRED_HEADING = re.compile(
    r"^\s*(?:requirements?|must[-\s]haves?|minimum qualifications?|what you(?:'| wi)ll need|"
    r"required skills?|basic qualifications?)\b",
    re.IGNORECASE,
)
_PREFERRED_HEADING = re.compile(
    r"^\s*(?:preferred|nice[-\s]to[-\s]haves?|bonus|plus(?:es)?|good to have|"
    r"additional qualifications?)\b",
    re.IGNORECASE,
)
_ANY_HEADING = re.compile(
    r"^\s*(?:responsibilities|what you(?:'| wi)ll do|about (?:the )?role|about us|benefits|perks)\b",
    re.IGNORECASE,
)
_YEARS = re.compile(r"(\d{1,2})\s*\+\s*(?:years?|yrs?)|(\d{1,2})\s*(?:years?|yrs?)[^.\n]{0,20}experience", re.IGNORECASE)
_DEGREE = re.compile(
    r"\b(bachelor(?:'s)?|b\.?\s?tech|b\.?\s?e\.?|b\.?sc|master(?:'s)?|m\.?\s?tech|m\.?\s?sc|mba|ph\.?\s?d)\b",
    re.IGNORECASE,
)
_DEGREE_LEVELS = {
    "bachelor": "bachelor",
    "b.tech": "bachelor",
    "btech": "bachelor",
    "b.e": "bachelor",
    "b.sc": "bachelor",
    "bsc": "bachelor",
    "master": "master",
    "m.tech": "master",
    "mtech": "master",
    "m.sc": "master",
    "msc": "master",
    "mba": "master",
    "ph.d": "doctorate",
    "phd": "doctorate",
}


def _clean(line: str) -> str:
    return re.sub(r"^\s*[-•*·–—]\s*", "", line).strip()


def _bucket_lines(description: str) -> dict[str, list[str]]:
    """Group lines under required / preferred / other by their section heading."""
    buckets: dict[str, list[str]] = {"required": [], "preferred": [], "other": []}
    current = "other"
    for raw in description.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _REQUIRED_HEADING.match(line):
            current = "required"
            continue
        if _PREFERRED_HEADING.match(line):
            current = "preferred"
            continue
        if _ANY_HEADING.match(line):
            current = "other"
            continue
        buckets[current].append(_clean(line))
    return buckets


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(value)
    return ordered


def extract_requirements(description: str) -> JobRequirements:
    buckets = _bucket_lines(description)

    required: list[str] = []
    preferred: list[str] = []

    for line in buckets["required"]:
        required.extend(find_skills(line))
    for line in buckets["preferred"]:
        preferred.extend(find_skills(line))

    # Without explicit headings, treat every mentioned skill as "required" only
    # when the sentence is imperative ("must", "required", "proficient in");
    # otherwise it is a preference. Guessing the other way would invent gaps.
    if not required and not preferred:
        for line in [*buckets["required"], *buckets["preferred"], *buckets["other"]]:
            found = find_skills(line)
            if not found:
                continue
            if re.search(r"\b(must|required|proficien\w*|strong|expert\w*|experience (?:with|in))\b", line, re.I):
                required.extend(found)
            else:
                preferred.extend(found)

    required = _dedupe(required)
    preferred = [skill for skill in _dedupe(preferred) if skill not in required]

    years: int | None = None
    year_match = _YEARS.search(description)
    if year_match:
        years = int(year_match.group(1) or year_match.group(2))

    degree: str | None = None
    degree_match = _DEGREE.search(description)
    if degree_match:
        # "Bachelor's" -> "bachelor": the possessive must not defeat the lookup,
        # which is how "Bachelor's degree required" was producing no requirement.
        raw = degree_match.group(0).lower().replace(" ", "").replace("'s", "")
        degree = _DEGREE_LEVELS.get(raw) or _DEGREE_LEVELS.get(raw.rstrip("."))

    responsibilities = [line for line in buckets["other"] if len(line.split()) >= 3][:10]

    return JobRequirements(
        required_skills=required,
        preferred_skills=preferred,
        min_years=years,
        degree_level=degree,
        responsibilities=responsibilities,
    )
