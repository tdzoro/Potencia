"""Language and readability criteria (LR-01 … LR-05).

LR-01 uses a mechanical issue detector rather than a grammar engine: repeated
words, doubled spacing, lower-case bullet starts and unbalanced brackets are
objective, reproducible and need no network. It is a proxy, and the module says
so rather than implying editorial judgement.
"""

from __future__ import annotations

import re
from statistics import mean

from app.intelligence.scoring.aggregate import (
    FILLER_OPENERS,
    FIRST_PERSON_WORDS,
    PASSIVE_RE,
    PAST_IRREGULAR,
    PRESENT_VERBS,
    clamp,
    lead_verb,
    make_finding,
    make_result,
    not_applicable,
    word_count,
)
from app.schemas.resume import Bullet, ExperienceEntry, ResumeStructure
from app.schemas.scores import CriterionResult, Evidence

REPEATED_WORD_RE = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)
DOUBLE_SPACE_RE = re.compile(r"[^\S\n]{2,}")
SENTENCE_TARGET = (12, 24)


def _corpus(structure: ResumeStructure) -> str:
    parts = [structure.summary.text or ""]
    parts.extend(bullet.text for bullet in structure.all_bullets())
    return " ".join(part for part in parts if part)


def _mechanical_issues(texts: list[str]) -> list[str]:
    issues: list[str] = []
    for text in texts:
        if DOUBLE_SPACE_RE.search(text):
            issues.append("double spacing")
        match = REPEATED_WORD_RE.search(text)
        if match:
            issues.append(f"repeated word '{match.group(1)}'")
        stripped = text.strip()
        if stripped and stripped[0].islower():
            issues.append("lower-case sentence start")
        if stripped.count("(") != stripped.count(")"):
            issues.append("unbalanced parentheses")
        if stripped.count("[") != stripped.count("]"):
            issues.append("unbalanced brackets")
    return issues


def _lr01(structure: ResumeStructure) -> CriterionResult:
    corpus = _corpus(structure)
    total_words = word_count(corpus)
    if total_words == 0:
        return not_applicable("LR-01", "no prose to inspect")

    texts = [structure.summary.text or "", *(bullet.text for bullet in structure.all_bullets())]
    issues = _mechanical_issues([text for text in texts if text])
    rate = len(issues) / total_words * 100
    subscore = clamp(1.0 - 0.05 * max(0.0, rate - 1.0))

    evidence = [Evidence(section="document", text=issue) for issue in issues[:3]] or [
        Evidence(section="summary", text=structure.summary.text or "document text")
    ]

    if subscore >= 0.999:
        return make_result("LR-01", 1.0, detail="no mechanical language issues", evidence=evidence)

    return make_result(
        "LR-01",
        subscore,
        detail=f"{len(issues)} mechanical issues across {total_words} words",
        evidence=evidence,
        findings=[
            make_finding(
                "LR-01",
                title="Mechanical language issues",
                explanation=(
                    "Repeated words, doubled spacing and unbalanced punctuation suggest the "
                    "text was not proof-read, which undermines otherwise strong content."
                ),
                remediation=(
                    "Re-read each flagged line and fix the punctuation or repetition. Reading "
                    "the bullets aloud catches most of these."
                ),
                evidence=evidence,
            )
        ],
    )


def _tense_of(text: str) -> str | None:
    lead = lead_verb(text)
    if not lead:
        return None
    if lead in PAST_IRREGULAR or lead.endswith("ed"):
        return "past"
    if lead in PRESENT_VERBS or lead.endswith("s"):
        return "present"
    return None


def _lr02(entries: list[ExperienceEntry]) -> CriterionResult:
    if not entries:
        return not_applicable("LR-02", "no roles to evaluate tense against")

    evaluated: list[tuple[bool, str, Bullet]] = []
    for entry in entries:
        current = entry.end is None or entry.date_precision == "present"
        for bullet in entry.bullets:
            tense = _tense_of(bullet.text)
            if tense is None:
                continue
            expected = "present" if current else "past"
            evaluated.append((tense == expected, tense, bullet))

    if not evaluated:
        return not_applicable("LR-02", "no bullet has a determinable tense")

    consistent = [item for item in evaluated if item[0]]
    subscore = len(consistent) / len(evaluated)
    wrong = [item for item in evaluated if not item[0]]

    evidence = [
        Evidence(section=f"bullets[{index}]", text=bullet.text)
        for index, (_, _, bullet) in enumerate(wrong[:3])
    ] or [Evidence(section="bullets[0]", text=evaluated[0][2].text)]

    if subscore >= 0.999:
        return make_result("LR-02", 1.0, detail="tense matches each role's status", evidence=evidence)

    return make_result(
        "LR-02",
        subscore,
        detail=f"{len(wrong)} of {len(evaluated)} bullets use the wrong tense",
        evidence=evidence,
        findings=[
            make_finding(
                "LR-02",
                title="Verb tense does not match the role's status",
                explanation=(
                    "A current role reads in the present tense; a finished role reads in the "
                    "past. Mixing them makes the timeline ambiguous."
                ),
                remediation=(
                    "Use present tense for what you currently do and past tense for completed "
                    "roles. Keep one tense within each role."
                ),
                evidence=evidence,
            )
        ],
    )


def _lr03(bullets: list[Bullet]) -> CriterionResult:
    if not bullets:
        return not_applicable("LR-03", "no bullets to evaluate")

    passive = [(index, bullet) for index, bullet in enumerate(bullets) if PASSIVE_RE.search(bullet.text)]
    ratio = len(passive) / len(bullets)
    subscore = clamp(1.0 - clamp(ratio / 0.5))

    evidence = [
        Evidence(section=f"bullets[{index}]", text=bullet.text) for index, bullet in passive[:3]
    ] or [Evidence(section="bullets[0]", text=bullets[0].text)]

    if subscore >= 0.999:
        return make_result("LR-03", 1.0, detail="active voice throughout", evidence=evidence)

    return make_result(
        "LR-03",
        subscore,
        detail=f"{len(passive)} of {len(bullets)} bullets are passive",
        evidence=evidence,
        findings=[
            make_finding(
                "LR-03",
                title="Passive voice obscures who did the work",
                explanation=(
                    "'Was migrated' does not say who migrated it, so the reader cannot credit "
                    "you with the result."
                ),
                remediation=(
                    "Rewrite each passive bullet so the sentence starts with you as the actor: "
                    "name the system you changed and what you did to it."
                ),
                evidence=evidence,
            )
        ],
    )


def _lr04(bullets: list[Bullet]) -> CriterionResult:
    if not bullets:
        return not_applicable("LR-04", "no bullets to measure")

    lengths = [word_count(bullet.text) for bullet in bullets]
    average = mean(lengths)
    low, high = SENTENCE_TARGET

    if low <= average <= high:
        subscore = 1.0
    elif average < low:
        subscore = clamp(1.0 - (low - average) / 12)
    else:
        subscore = clamp(1.0 - (average - high) / 12)

    evidence = [Evidence(section="bullets", text=f"mean {average:.0f} words per bullet")]

    if subscore >= 0.999:
        return make_result("LR-04", 1.0, detail=f"mean {average:.0f} words per bullet", evidence=evidence)

    return make_result(
        "LR-04",
        subscore,
        detail=f"mean {average:.0f} words per bullet, target {low}–{high}",
        evidence=evidence,
        findings=[
            make_finding(
                "LR-04",
                title="Bullets fall outside a comfortable length",
                explanation=(
                    "Very short bullets lack context; very long ones bury the result in the "
                    "middle of a sentence."
                ),
                remediation=(
                    "Aim for one idea per bullet. Split any bullet carrying two results, and "
                    "add the missing context to any bullet that is a fragment."
                ),
                evidence=evidence,
            )
        ],
    )


def _lr05(structure: ResumeStructure) -> CriterionResult:
    texts = [structure.summary.text or "", *(bullet.text for bullet in structure.all_bullets())]
    texts = [text for text in texts if text]
    if not texts:
        return not_applicable("LR-05", "no prose to inspect")

    hits: list[str] = []
    for text in texts:
        for word in re.findall(r"[A-Za-z']+", text.lower()):
            if word in FIRST_PERSON_WORDS:
                hits.append(word)
        if lead_verb(text) in FILLER_OPENERS:
            hits.append(lead_verb(text))

    subscore = clamp(1.0 - 0.1 * min(len(hits), 10))
    evidence = [Evidence(section="document", text=", ".join(sorted(set(hits))))] if hits else [
        Evidence(section="summary", text=structure.summary.text or texts[0])
    ]

    if not hits:
        return make_result("LR-05", 1.0, detail="no first-person pronouns or filler openers", evidence=evidence)

    return make_result(
        "LR-05",
        subscore,
        detail=f"{len(hits)} first-person pronoun(s) or filler opener(s)",
        evidence=evidence,
        findings=[
            make_finding(
                "LR-05",
                title="First-person pronouns and filler openers",
                explanation=(
                    "Resumes are written in implied first person. Explicit pronouns waste "
                    "characters and read as informal."
                ),
                remediation=(
                    "Delete 'I', 'my', 'we' and start the bullet at the verb instead. Replace "
                    "'responsible for' with what you actually delivered."
                ),
                evidence=evidence,
            )
        ],
    )


def evaluate(structure: ResumeStructure) -> list[CriterionResult]:
    bullets = structure.all_bullets()
    return [
        _lr01(structure),
        _lr02(structure.experience),
        _lr03(bullets),
        _lr04(bullets),
        _lr05(structure),
    ]
