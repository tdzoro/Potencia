"""Content quality criteria (CQ-01 … CQ-05).

Ownership note (§6): this module never judges verb *quality* in CQ-02 (that is
CQ-04's property) and never counts a missing metric as a structural problem
(that is CQ-03's). Each defect is deducted once.
"""

from __future__ import annotations

import re

from app.intelligence.scoring.aggregate import (
    FIRST_PERSON_RE,
    GENERIC_PHRASES,
    WEAK_VERBS,
    clamp,
    has_quantification,
    is_verb_lead,
    lead_verb,
    make_finding,
    make_result,
    not_applicable,
    word_count,
)
from app.schemas.resume import Bullet, ResumeStructure
from app.schemas.scores import CriterionResult, Evidence

# Roles a summary normally names. Absence is a real signal, not a style opinion.
ROLE_WORDS = frozenset(
    {
        "engineer", "developer", "analyst", "designer", "manager", "scientist",
        "architect", "consultant", "intern", "administrator", "specialist",
        "researcher", "lead", "student", "graduate",
    }
)


def _bullets(structure: ResumeStructure) -> list[Bullet]:
    return structure.all_bullets()


def _cq01_summary(structure: ResumeStructure) -> CriterionResult:
    text = (structure.summary.text or "").strip()

    if not structure.summary.present or not text:
        evidence = [Evidence(section="summary", text="<no professional summary found>")]
        return make_result(
            "CQ-01",
            0.0,
            detail="no summary section",
            evidence=evidence,
            findings=[
                make_finding(
                    "CQ-01",
                    title="No professional summary",
                    explanation=(
                        "A reader spends the first seconds deciding whether to keep going. "
                        "Without a summary there is nothing targeted at the top of the page."
                    ),
                    remediation=(
                        "Add three lines naming the role you are targeting, the domain you "
                        "work in, and one thing you do measurably better than most. Avoid "
                        "adjectives you cannot support with evidence elsewhere."
                    ),
                    evidence=evidence,
                )
            ],
        )

    misses: list[str] = []
    count = word_count(text)
    if not 20 <= count <= 80:
        misses.append(f"it runs to {count} words, outside the 20–80 range")
    if FIRST_PERSON_RE.search(text):
        misses.append("it uses first-person pronouns")
    if not any(word in ROLE_WORDS for word in re.findall(r"[a-z]+", text.lower())):
        misses.append("it does not name a target role")

    evidence = [Evidence(section="summary", text=text)]
    if not misses:
        return make_result("CQ-01", 1.0, detail="summary meets all checks", evidence=evidence)

    subscore = 0.7 if len(misses) == 1 else 0.4
    return make_result(
        "CQ-01",
        subscore,
        detail="; ".join(misses),
        evidence=evidence,
        findings=[
            make_finding(
                "CQ-01",
                title="The summary is not doing its job",
                explanation="The summary " + " and ".join(misses) + ".",
                remediation=(
                    "Rewrite the summary as three sentences: the role you target, the domain "
                    "experience you bring, and the outcome you produce. Drop first-person "
                    "phrasing — resumes are written in implied first person."
                    if FIRST_PERSON_RE.search(text)
                    else "Tighten the summary to three sentences naming the role you target, "
                    "the domain you work in, and the outcome you produce."
                ),
                evidence=evidence,
            )
        ],
    )


def _cq02_structure(bullets: list[Bullet]) -> CriterionResult:
    if not bullets:
        return not_applicable("CQ-02", "no bullets to evaluate")

    failing: list[tuple[int, Bullet]] = []
    for index, bullet in enumerate(bullets):
        length = word_count(bullet.text)
        if not (is_verb_lead(bullet.text) and 4 <= length <= 40):
            failing.append((index, bullet))

    ratio = (len(bullets) - len(failing)) / len(bullets)
    subscore = clamp(ratio / 0.8)
    evidence = [
        Evidence(section=f"bullets[{index}]", text=bullet.text)
        for index, bullet in failing[:3]
    ] or [Evidence(section="bullets[0]", text=bullets[0].text)]

    if subscore >= 0.999:
        return make_result("CQ-02", 1.0, detail="bullets are well formed", evidence=evidence)

    return make_result(
        "CQ-02",
        subscore,
        detail=f"{len(failing)} of {len(bullets)} bullets are not well formed",
        evidence=evidence,
        findings=[
            make_finding(
                "CQ-02",
                title="Some bullets are not complete statements",
                explanation=(
                    "A bullet that does not open with an action verb and carry an object "
                    "reads as a label rather than an achievement."
                ),
                remediation=(
                    "Open every bullet with a verb and give it an object: what you acted on, "
                    "for whom or at what scale. If a line is a bare skill name, move it to "
                    "the skills section."
                ),
                evidence=evidence,
            )
        ],
    )


def _cq03_quantification(bullets: list[Bullet]) -> CriterionResult:
    if not bullets:
        return not_applicable("CQ-03", "no bullets to evaluate")

    unquantified = [(index, bullet) for index, bullet in enumerate(bullets) if not has_quantification(bullet.text)]
    ratio = (len(bullets) - len(unquantified)) / len(bullets)
    subscore = clamp(ratio / 0.5)
    evidence = [
        Evidence(section=f"bullets[{index}]", text=bullet.text)
        for index, bullet in unquantified[:3]
    ] or [Evidence(section="bullets[0]", text=bullets[0].text)]

    if subscore >= 0.999:
        return make_result("CQ-03", 1.0, detail="achievements are quantified", evidence=evidence)

    return make_result(
        "CQ-03",
        subscore,
        detail=f"{len(unquantified)} of {len(bullets)} bullets carry no measurable outcome",
        evidence=evidence,
        findings=[
            make_finding(
                "CQ-03",
                title="Achievements are described but not measured",
                explanation=(
                    "Without a number, percentage, duration or explicit scale the reader "
                    "cannot judge whether the work was significant."
                ),
                remediation=(
                    "For each of these bullets, what was the real scale — records processed, "
                    "requests per day, users affected, time saved, team size? Add the figure "
                    "you can defend in an interview. If a task genuinely has no measurable "
                    "outcome, say what changed as a result instead."
                ),
                evidence=evidence,
            )
        ],
    )


def _cq04_verbs(bullets: list[Bullet]) -> CriterionResult:
    if not bullets:
        return not_applicable("CQ-04", "no bullets to evaluate")

    leads = [lead_verb(bullet.text) for bullet in bullets]
    variety = clamp(len({lead for lead in leads if lead}) / len(bullets))
    # `lead_verb` already ran once above; re-extracting it here doubled the work
    # for every bullet in the document.
    weak = [
        (index, bullet)
        for index, (bullet, lead) in enumerate(zip(bullets, leads, strict=True))
        if lead in WEAK_VERBS
    ]
    subscore = clamp(variety * (1.0 - 0.1 * min(len(weak), 5)))

    evidence = [
        Evidence(section=f"bullets[{index}]", text=bullet.text) for index, bullet in weak[:3]
    ] or [Evidence(section="bullets[0]", text=bullets[0].text)]

    if subscore >= 0.999:
        return make_result("CQ-04", 1.0, detail="verbs are varied and specific", evidence=evidence)

    return make_result(
        "CQ-04",
        subscore,
        detail=f"{len(weak)} bullets open with a weak verb",
        evidence=evidence,
        findings=[
            make_finding(
                "CQ-04",
                title="Bullets open with weak or repeated verbs",
                explanation=(
                    "Verbs such as 'worked on', 'helped' or 'responsible for' describe "
                    "presence, not contribution, and repeat across the page."
                ),
                remediation=(
                    "Replace each weak opener with the verb that names what you actually did — "
                    "built, migrated, reduced, owned, shipped. Vary them across bullets so no "
                    "verb repeats more than twice."
                ),
                evidence=evidence,
            )
        ],
    )


def _cq05_specificity(structure: ResumeStructure, bullets: list[Bullet]) -> CriterionResult:
    text = " ".join([structure.summary.text or "", *(bullet.text for bullet in bullets)]).lower()
    hits = [phrase for phrase in GENERIC_PHRASES if phrase in text]
    subscore = clamp(1.0 - 0.1 * min(len(hits), 10))

    corpus_evidence = [
        Evidence(
            section="summary" if structure.summary.text and phrase in (structure.summary.text or "").lower() else "bullets",
            text=phrase,
        )
        for phrase in hits[:3]
    ]

    if not hits:
        return make_result(
            "CQ-05",
            1.0,
            detail="no generic filler detected",
            evidence=[Evidence(section="summary", text=structure.summary.text or "document text")],
        )

    return make_result(
        "CQ-05",
        subscore,
        detail=f"{len(hits)} generic phrases: {', '.join(hits)}",
        evidence=corpus_evidence,
        findings=[
            make_finding(
                "CQ-05",
                title="Generic phrases dilute the page",
                explanation=(
                    "Phrases like '" + hits[0] + "' are claimed by nearly every applicant, so "
                    "they consume space without distinguishing you."
                ),
                remediation=(
                    "Delete the generic phrases and replace the space with a specific: the "
                    "technology you used, the domain you worked in, or the outcome you produced."
                ),
                evidence=corpus_evidence,
            )
        ],
    )


def evaluate(structure: ResumeStructure) -> list[CriterionResult]:
    bullets = _bullets(structure)
    return [
        _cq01_summary(structure),
        _cq02_structure(bullets),
        _cq03_quantification(bullets),
        _cq04_verbs(bullets),
        _cq05_specificity(structure, bullets),
    ]
