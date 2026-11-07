"""Experience criteria (EX-01 … EX-05).

Duty statements are owned by EX-03; missing metrics by CQ-03 and passive voice
by LR-03. This module therefore reads for *outcome language only* and never
re-penalises a bullet for what another criterion owns.
"""

from __future__ import annotations

import re
from statistics import median

from app.intelligence.scoring.aggregate import (
    clamp,
    experience_is_applicable,
    has_result_indicator,
    make_finding,
    make_result,
    not_applicable,
)
from app.intelligence.taxonomy import split_supported_skills
from app.schemas.resume import ExperienceEntry, ResumeStructure
from app.schemas.scores import CriterionResult, Evidence

_YEAR_MONTH = re.compile(r"(?P<year>(?:19|20)\d{2})(?:[-/](?P<month>0?[1-9]|1[0-2]))?")

SENIORITY = {
    "intern": 0,
    "trainee": 0,
    "apprentice": 0,
    "junior": 1,
    "associate": 1,
    "engineer": 2,
    "developer": 2,
    "analyst": 2,
    "designer": 2,
    "scientist": 2,
    "senior": 3,
    "lead": 4,
    "staff": 4,
    "principal": 5,
    "architect": 5,
    "manager": 5,
    "head": 6,
    "director": 6,
}


def parse_year_month(value: str | None) -> tuple[int, int] | None:
    """Parse `2024-06`, `06/2024`-free formats and bare years. Unknown is None."""
    if not value:
        return None
    match = _YEAR_MONTH.search(value)
    if not match:
        return None
    year = int(match.group("year"))
    month = int(match.group("month") or 1)
    return year, month


def _months_between(start: tuple[int, int], end: tuple[int, int]) -> int:
    return (end[0] - start[0]) * 12 + (end[1] - start[1])


def _seniority(title: str | None) -> int | None:
    if not title:
        return None
    lowered = title.lower()
    ranks = [rank for word, rank in SENIORITY.items() if word in lowered]
    return max(ranks) if ranks else 2


def _ex01(entries: list[ExperienceEntry]) -> CriterionResult:
    if not entries:
        return not_applicable("EX-01", "no roles to evaluate")

    incomplete = [
        entry
        for entry in entries
        if not (entry.title and entry.organisation and entry.start)
    ]
    evidence = [
        Evidence(
            section=f"experience[{index}]",
            text=" ".join(filter(None, [entry.title, entry.organisation, entry.start]))
            or "<incomplete entry>",
        )
        for index, entry in enumerate(entries)
        if entry in incomplete
    ] or [Evidence(section="experience[0]", text=entries[0].title or "<entry>")]

    if not incomplete:
        return make_result("EX-01", 1.0, detail="every role is fully specified", evidence=evidence)

    return make_result(
        "EX-01",
        0.0,
        detail=f"{len(incomplete)} of {len(entries)} roles lack a title, organisation or start date",
        evidence=evidence,
        findings=[
            make_finding(
                "EX-01",
                title="A role is missing its title, employer or dates",
                explanation=(
                    "Recruiters and parsers both key on title, organisation and dates. A role "
                    "missing any of them is hard to place in a timeline or a seniority band."
                ),
                remediation=(
                    "State the job title, the organisation, and the start date for each role. "
                    "If the role was unofficial or a placement, name it as such rather than "
                    "leaving the field empty."
                ),
                evidence=evidence,
            )
        ],
    )


def _ex02(entries: list[ExperienceEntry]) -> CriterionResult:
    if not entries:
        return not_applicable("EX-02", "no roles to evaluate")

    problems: list[str] = []
    parsed: list[tuple[int, tuple[int, int], tuple[int, int] | None]] = []

    for index, entry in enumerate(entries):
        start = parse_year_month(entry.start)
        if start is None:
            problems.append(f"experience[{index}] has no parseable start date")
            continue
        end = None
        if entry.end and entry.date_precision != "present":
            end = parse_year_month(entry.end)
            if end is not None and _months_between(start, end) < 0:
                problems.append(f"experience[{index}] ends before it starts")
        parsed.append((index, start, end))

    # Reverse-chronological: starts must not increase as we walk the document.
    for previous, current in zip(parsed, parsed[1:]):
        if current[1] > previous[1]:
            problems.append(
                f"experience[{current[0]}] begins before experience[{previous[0]}] but is listed after it"
            )

    # Unexplained gaps longer than six months between consecutive roles.
    ordered = sorted((item for item in parsed if item[2] is not None), key=lambda item: item[1])
    for previous, current in zip(ordered, ordered[1:]):
        gap = _months_between(previous[2], current[1])  # type: ignore[arg-type]
        if gap > 6:
            problems.append(
                f"a gap of {gap} months separates experience[{previous[0]}] from experience[{current[0]}]"
            )

    evidence = [
        Evidence(section="experience", text=problem) for problem in problems[:3]
    ] or [Evidence(section="experience[0]", text=entries[0].title or "<entry>")]

    subscore = clamp(1.0 - 0.25 * len(problems))
    if subscore >= 0.999:
        return make_result("EX-02", 1.0, detail="chronology is clean", evidence=evidence)

    return make_result(
        "EX-02",
        subscore,
        detail="; ".join(problems[:3]),
        evidence=evidence,
        findings=[
            make_finding(
                "EX-02",
                title="The work history timeline does not add up",
                explanation="; ".join(problems[:3]) + ".",
                remediation=(
                    "Order roles newest first, correct any end date that precedes its start, "
                    "and account for gaps longer than six months in one line — study, "
                    "freelance, caregiving or job search are all acceptable."
                ),
                evidence=evidence,
            )
        ],
    )


def _ex03(entries: list[ExperienceEntry]) -> CriterionResult:
    bullets = [bullet for entry in entries for bullet in entry.bullets]
    if not bullets:
        return not_applicable("EX-03", "no bullets to evaluate")

    duties = [(index, bullet) for index, bullet in enumerate(bullets) if not has_result_indicator(bullet.text)]
    ratio = (len(bullets) - len(duties)) / len(bullets)
    subscore = clamp(ratio / 0.6)
    evidence = [
        Evidence(section=f"bullets[{index}]", text=bullet.text) for index, bullet in duties[:3]
    ] or [Evidence(section="bullets[0]", text=bullets[0].text)]

    if subscore >= 0.999:
        return make_result("EX-03", 1.0, detail="bullets assert outcomes", evidence=evidence)

    return make_result(
        "EX-03",
        subscore,
        detail=f"{len(duties)} of {len(bullets)} bullets state a duty rather than an outcome",
        evidence=evidence,
        findings=[
            make_finding(
                "EX-03",
                title="Bullets list duties instead of results",
                explanation=(
                    "A duty statement says what you were assigned. An outcome says what changed "
                    "because you did it, which is the only part a reader can evaluate."
                ),
                remediation=(
                    "For each of these bullets, what changed afterwards? Name the result — "
                    "what got faster, cheaper, safer or possible that was not before. Keep it "
                    "to what you can defend in an interview."
                ),
                evidence=evidence,
            )
        ],
    )


def _ex04(entries: list[ExperienceEntry]) -> CriterionResult:
    if len(entries) < 1:
        return not_applicable("EX-04", "no roles to evaluate")

    dated = []
    for entry in entries:
        start = parse_year_month(entry.start)
        end = parse_year_month(entry.end) if entry.end else None
        rank = _seniority(entry.title)
        if start and rank is not None:
            dated.append((start, end, rank))

    if not dated:
        return not_applicable("EX-04", "no parseable dates or titles")

    tenures = [
        _months_between(start, end) for start, end, _ in dated if end is not None
    ]
    median_tenure = median(tenures) if tenures else None

    dated.sort(key=lambda item: item[0])
    first_rank, last_rank = dated[0][2], dated[-1][2]

    evidence = [Evidence(section="experience", text=entry.title or "<role>") for entry in entries[:3]]

    if last_rank > first_rank and (median_tenure is None or median_tenure >= 12):
        return make_result("EX-04", 1.0, detail="titles show progression", evidence=evidence)

    subscore = 0.3 if (last_rank < first_rank or (median_tenure is not None and median_tenure < 6)) else 0.6
    reason = (
        "seniority falls across the history"
        if last_rank < first_rank
        else "no clear progression in titles"
    )
    return make_result(
        "EX-04",
        subscore,
        detail=reason,
        evidence=evidence,
        findings=[
            make_finding(
                "EX-04",
                title="Career progression is not legible",
                explanation=(
                    "The titles do not show a rising trajectory, so a reader cannot tell "
                    "whether responsibility grew. This is a soft signal and is scored gently."
                ),
                remediation=(
                    "Where responsibility did grow, make it visible in the title or in the "
                    "first bullet of the role — for example scope, team size or ownership. "
                    "If the trajectory is not linear, one line of context prevents misreading."
                ),
                evidence=evidence,
            )
        ],
    )


def _ex05(structure: ResumeStructure, entries: list[ExperienceEntry]) -> CriterionResult:
    claimed = {name.lower().strip() for name in structure.skills.explicit if name.strip()}
    if not claimed:
        return not_applicable("EX-05", "no claimed skills to cross-check against experience")

    text = structure.experience_text()
    matched, _ = split_supported_skills(text, claimed)
    ratio = len(matched) / len(claimed)
    subscore = clamp(ratio / 0.5)

    evidence = [Evidence(section="skills", text=", ".join(sorted(claimed)[:5]))]
    if subscore >= 0.999:
        return make_result("EX-05", 1.0, detail="experience supports the claimed skills", evidence=evidence)

    return make_result(
        "EX-05",
        subscore,
        detail=f"{len(claimed) - len(matched)} claimed skills never appear in the experience",
        evidence=evidence,
        findings=[
            make_finding(
                "EX-05",
                title="Claimed skills are disconnected from the experience",
                explanation=(
                    "Skills listed at the top are more convincing when the work history shows "
                    "them in use. The overlap here is thin."
                ),
                remediation=(
                    "For the skills that matter most for the role you want, add a bullet where "
                    "you actually used them. If a listed skill was never used in a role, "
                    "consider removing it rather than leaving it unsupported."
                ),
                evidence=evidence,
            )
        ],
    )


def evaluate(structure: ResumeStructure) -> list[CriterionResult]:
    if not experience_is_applicable(structure):
        return [
            not_applicable(
                "EX-01",
                "no work history: experience is not applicable for this candidate",
            ),
            not_applicable("EX-02", "no work history"),
            not_applicable("EX-03", "no work history"),
            not_applicable("EX-04", "no work history"),
            not_applicable("EX-05", "no work history"),
        ]

    entries = structure.experience
    return [
        _ex01(entries),
        _ex02(entries),
        _ex03(entries),
        _ex04(entries),
        _ex05(structure, entries),
    ]
