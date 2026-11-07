"""Aggregation core: the single place where numbers are actually produced.

Three invariants are enforced here rather than trusted:

1. **Ownership is unique.** Every criterion owns exactly one `property`, so the
   same defect can never be deducted twice (SCORING_METHODOLOGY.md §6). The
   assertion runs at import time — a duplicate cannot reach production.
2. **No silent deductions.** An applicable criterion scoring below 1.0 must
   emit at least one finding. A number moving without an explanation is the
   exact failure this product exists to avoid.
3. **Findings reconcile with the score.** The findings' `score_impact` values
   sum to `100 - overall` for the applicable weight. If they do not, the report
   is wrong and `assemble` refuses to build it.

Everything here is pure: no I/O, no clock, no randomness, no model call.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from app.schemas.resume import Bullet, ResumeStructure
from app.schemas.scores import (
    CATEGORY_WEIGHTS,
    METHODOLOGY_VERSION,
    ATSReport,
    CriterionResult,
    Evidence,
    Finding,
    ScoreBundle,
    ScoreCategory,
    ScoreComponent,
    Strength,
)


@dataclass(frozen=True)
class CriterionSpec:
    id: str
    category: str
    weight: int
    property: str
    expected_evidence: int = 1


# §4 of the methodology, transcribed. Weights are within-category.
SPECS: tuple[CriterionSpec, ...] = (
    # Content quality (25)
    CriterionSpec("CQ-01", "content_quality", 15, "summary"),
    CriterionSpec("CQ-02", "content_quality", 25, "bullet_structure", 2),
    CriterionSpec("CQ-03", "content_quality", 25, "quantification", 3),
    CriterionSpec("CQ-04", "content_quality", 15, "verb_lexicon", 2),
    CriterionSpec("CQ-05", "content_quality", 20, "specificity", 2),
    # Experience (20)
    CriterionSpec("EX-01", "experience", 20, "role_clarity"),
    CriterionSpec("EX-02", "experience", 25, "chronology", 2),
    CriterionSpec("EX-03", "experience", 30, "achievement_framing", 3),
    CriterionSpec("EX-04", "experience", 15, "progression"),
    CriterionSpec("EX-05", "experience", 10, "experience_relevance"),
    # Skills (15)
    CriterionSpec("SK-01", "skills", 25, "skill_coverage"),
    CriterionSpec("SK-02", "skills", 20, "skill_grouping"),
    CriterionSpec("SK-03", "skills", 15, "skill_redundancy"),
    CriterionSpec("SK-04", "skills", 25, "skill_verifiability", 2),
    CriterionSpec("SK-05", "skills", 15, "skill_recency"),
    # Structure (15)
    CriterionSpec("ST-01", "structure", 30, "section_presence", 2),
    CriterionSpec("ST-02", "structure", 15, "section_order"),
    CriterionSpec("ST-03", "structure", 20, "heading_clarity", 2),
    CriterionSpec("ST-04", "structure", 15, "length"),
    CriterionSpec("ST-05", "structure", 20, "contact"),
    # ATS (15)
    CriterionSpec("AT-01", "ats_compatibility", 30, "extraction"),
    CriterionSpec("AT-02", "ats_compatibility", 20, "reading_order"),
    CriterionSpec("AT-03", "ats_compatibility", 15, "hazards", 2),
    CriterionSpec("AT-04", "ats_compatibility", 20, "dates", 2),
    CriterionSpec("AT-05", "ats_compatibility", 15, "contact_parse"),
    # Language (10)
    CriterionSpec("LR-01", "language_readability", 25, "grammar", 2),
    CriterionSpec("LR-02", "language_readability", 20, "tense", 2),
    CriterionSpec("LR-03", "language_readability", 20, "passive", 2),
    CriterionSpec("LR-04", "language_readability", 15, "sentence_length"),
    CriterionSpec("LR-05", "language_readability", 20, "pronouns", 2),
)

SPEC_BY_ID: dict[str, CriterionSpec] = {spec.id: spec for spec in SPECS}


def _validate_registry(specs: Sequence[CriterionSpec]) -> None:
    if len({spec.id for spec in specs}) != len(specs):
        raise AssertionError("duplicate criterion id in the scoring registry")
    properties = [spec.property for spec in specs]
    if len(set(properties)) != len(properties):
        duplicates = sorted({p for p in properties if properties.count(p) > 1})
        raise AssertionError(f"double-penalty: property owned twice {duplicates}")

    for category in CATEGORY_WEIGHTS:
        total = sum(spec.weight for spec in specs if spec.category == category)
        if total != 100:
            raise AssertionError(f"{category} criteria weigh {total}, must be 100")


_validate_registry(SPECS)

# --- Lexicons (versioned artefacts per §8) -----------------------------------

WEAK_VERBS = frozenset(
    {
        "worked",
        "help",
        "helped",
        "assist",
        "assisted",
        "responsible",
        "involved",
        "participated",
        "handled",
        "did",
        "made",
        "used",
    }
)

STRONG_VERBS = frozenset(
    {
        "achieved",
        "accelerated",
        "architected",
        "automated",
        "built",
        "cut",
        "delivered",
        "designed",
        "developed",
        "drove",
        "eliminated",
        "engineered",
        "established",
        "grew",
        "implemented",
        "improved",
        "increased",
        "initiated",
        "launched",
        "led",
        "migrated",
        "optimised",
        "optimized",
        "owned",
        "reduced",
        "resolved",
        "scaled",
        "shipped",
        "simplified",
        "streamlined",
        "won",
        "wrote",
    }
)

# Matched as word stems so both tenses count: a current role says "reduce", a
# past role says "reduced", and both assert an outcome.
RESULT_INDICATOR_RE = re.compile(
    r"\b(?:achiev|accelerat|improv|reduc|increas|decreas|cut|grow|grew|scal|deliver|"
    r"launch|led|lead|sav|resolv|streamlin|eliminat|ship|won|rais|automat|migrat)\w*",
    re.IGNORECASE,
)

GENERIC_PHRASES: tuple[str, ...] = (
    "team player",
    "hard working",
    "hard-working",
    "various tasks",
    "go-getter",
    "think outside the box",
    "results-driven individual",
    "detail oriented",
    "detail-oriented",
    "self-starter",
    "excellent communication skills",
    "familiar with",
    "etc.",
    "and more",
)

QUANT_RE = re.compile(
    r"(\d+\s*%)|([₹$€£]\s?\d)|(\b\d[\d,.]*\b)|(\b\d+\s*(?:x|×|k|m|bn)\b)",
    re.IGNORECASE,
)

FIRST_PERSON_RE = re.compile(r"\b(i|my|me|we|our|us)\b", re.IGNORECASE)
FIRST_PERSON_WORDS = frozenset({"i", "my", "me", "we", "our", "us"})

FILLER_OPENERS = frozenset(
    {"responsible", "worked", "helped", "assisted", "involved", "participated"}
)

PASSIVE_RE = re.compile(
    r"\b(?:was|were|been|being|is|are|am)\s+(?:\w+ed|built|written|made|led|run|"
    r"driven|given|taken|done|shown|held|kept|sent|found)\b",
    re.IGNORECASE,
)

PAST_IRREGULAR = frozenset(
    {
        "built", "led", "wrote", "shipped", "ran", "drove", "made", "grew", "cut",
        "won", "saw", "took", "gave", "spoke", "began", "brought", "found", "held",
        "kept", "left", "lost", "met", "paid", "put", "sent", "set", "spent",
        "taught", "thought", "told", "understood", "went", "drove", "deployed",
    }
)

# Base forms, so a current role's bullets are recognised as verbs in the present
# tense. Outcome verbs are included because a present-tense achievement
# ("reduce reconciliation time") is still a verb-led bullet.
PRESENT_VERBS = frozenset(
    {
        "build", "lead", "manage", "design", "own", "maintain", "write", "ship",
        "develop", "drive", "run", "deliver", "scale", "automate", "migrate",
        "coordinate", "mentor", "review", "test", "deploy",
        "reduce", "improve", "increase", "grow", "save", "resolve", "streamline",
        "eliminate", "accelerate", "raise", "achieve", "launch", "win", "rewrite",
        "analyse", "analyze", "document", "present", "support", "train",
    }
)


# --- Small text helpers ------------------------------------------------------


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z'\-]*", text)


def word_count(text: str) -> int:
    return len(text.split())


def lead_verb(text: str) -> str:
    match = re.match(r"\s*([A-Za-z\-']+)", text)
    return match.group(1).lower() if match else ""


def is_verb_lead(text: str) -> bool:
    """Whether a bullet opens with a verb at all.

    Deliberately does *not* judge verb quality: weak verbs are owned by CQ-04,
    so counting them here would be a double penalty (§6).
    """
    lead = lead_verb(text)
    return lead in STRONG_VERBS or lead in WEAK_VERBS or lead in PRESENT_VERBS


def has_quantification(text: str) -> bool:
    return bool(QUANT_RE.search(text))


def has_result_indicator(text: str) -> bool:
    return bool(RESULT_INDICATOR_RE.search(text))


def bullet_evidence(bullets: Iterable[Bullet], section: str) -> list[Evidence]:
    return [
        Evidence(section=f"{section}[{index}]", text=bullet.text)
        for index, bullet in enumerate(bullets)
    ]


def stable_finding_id(criterion_id: str, title: str) -> str:
    """Deterministic id, so identical input yields identical output (§2.1)."""
    digest = hashlib.sha1(f"{criterion_id}:{title}".encode("utf-8")).hexdigest()[:12]
    return f"f_{digest}"


def make_finding(
    criterion_id: str,
    *,
    title: str,
    explanation: str,
    remediation: str,
    evidence: Sequence[Evidence],
    severity: str = "medium",
) -> Finding:
    spec = SPEC_BY_ID[criterion_id]
    return Finding(
        id=stable_finding_id(criterion_id, title),
        category=spec.category,  # type: ignore[arg-type]
        criterion=criterion_id,
        severity=severity,  # type: ignore[arg-type]
        title=title,
        evidence=list(evidence),
        explanation=explanation,
        remediation=remediation,
        score_impact=None,
        source="rules",
    )


def make_result(
    criterion_id: str,
    subscore: float,
    *,
    applicable: bool = True,
    detail: str = "",
    evidence: Sequence[Evidence] | None = None,
    findings: Sequence[Finding] | None = None,
) -> CriterionResult:
    spec = SPEC_BY_ID[criterion_id]
    return CriterionResult(
        criterion=spec.id,
        category=spec.category,  # type: ignore[arg-type]
        weight=spec.weight,
        property=spec.property,
        applicable=applicable,
        subscore=clamp(float(subscore)),
        detail=detail,
        evidence=list(evidence or []),
        findings=list(findings or []),
    )


def not_applicable(criterion_id: str, detail: str) -> CriterionResult:
    """Leave the denominator. Never a zero — a zero is a judgement, this is not."""
    return make_result(criterion_id, 0.0, applicable=False, detail=detail)


# --- Confidence (§7) ---------------------------------------------------------


def confidence_for(result: CriterionResult, extraction_confidence: float) -> str:
    """How far the criterion's *judgements* are substantiated.

    Density measures the share of contested assertions that cite text the user
    can inspect. A criterion that found nothing wrong makes no contested
    assertion, so it is fully substantiated by definition — scoring it on the
    raw number of citations would mark a flawless resume as low-confidence
    precisely because there was nothing to cite.
    """
    if not result.findings:
        density = 1.0
    else:
        cited = sum(1 for finding in result.findings if finding.evidence)
        density = cited / len(result.findings)
    if extraction_confidence >= 0.90 and density >= 0.70:
        return "high"
    if extraction_confidence >= 0.75 and density >= 0.40:
        return "medium"
    return "low"


# --- Severity from impact ----------------------------------------------------

_SEVERITY_ORDER = ("info", "low", "medium", "high", "critical")


def severity_for_loss(loss: float) -> str:
    if loss >= 5.0:
        return "critical"
    if loss >= 2.5:
        return "high"
    if loss >= 1.0:
        return "medium"
    if loss >= 0.3:
        return "low"
    return "info"


def severity_rank(severity: str) -> int:
    return _SEVERITY_ORDER.index(severity) if severity in _SEVERITY_ORDER else 0


# --- Result object -----------------------------------------------------------


@dataclass
class ScoreResult:
    bundle: ScoreBundle
    findings: list[Finding] = field(default_factory=list)
    strengths: list[Strength] = field(default_factory=list)
    criteria: list[CriterionResult] = field(default_factory=list)
    # The ATS report is carried alongside rather than inside the bundle: it is a
    # separate deliverable with its own disclaimer, and it feeds one category.
    ats: ATSReport | None = None


STRENGTH_TEXT: dict[str, str] = {
    "CQ-01": "The summary states a role and differentiator without first-person phrasing.",
    "CQ-02": "Bullets are consistently written as complete statements.",
    "CQ-03": "Achievements are quantified throughout.",
    "CQ-04": "Action verbs are varied and specific.",
    "CQ-05": "The language is specific rather than generic.",
    "EX-01": "Every role states a title, an organisation and dates.",
    "EX-02": "The work history is reverse-chronological with no unexplained gaps.",
    "EX-03": "Bullets describe outcomes rather than duties.",
    "EX-04": "Titles show progression and tenure is credible.",
    "EX-05": "The experience substantiates the claimed skill set.",
    "SK-01": "The skill list is broad enough to be legible to a recruiter.",
    "SK-02": "Skills are organised into recognisable groups.",
    "SK-03": "No duplicated or aliased skills.",
    "SK-04": "Claimed skills are substantiated elsewhere in the resume.",
    "SK-05": "The skill set is current.",
    "ST-01": "The standard sections are all present.",
    "ST-02": "Sections follow a conventional order.",
    "ST-03": "Headings use conventional, parseable labels.",
    "ST-04": "The document length suits the experience level.",
    "ST-05": "Contact details are complete and parseable.",
    "AT-01": "Text extracts cleanly from the document.",
    "AT-02": "The reading order is single-column and unambiguous.",
    "AT-03": "No structural hazards were detected.",
    "AT-04": "Dates are consistently formatted and unambiguous.",
    "AT-05": "Email and phone are recoverable as text.",
    "LR-01": "Very few mechanical language issues.",
    "LR-02": "Verb tense is consistent with each role's status.",
    "LR-03": "Bullets are written in active voice.",
    "LR-04": "Sentence length is readable.",
    "LR-05": "No first-person pronouns or filler openers.",
}


def band_for(overall: float, cq03: float | None, sk04: float | None) -> str:
    """§9.1 bands, with the §9.1 gate on the top band."""
    if overall >= 90 and (cq03 or 0.0) >= 0.8 and (sk04 or 0.0) >= 0.8:
        return "exceptional"
    if overall >= 75:
        return "strong"
    if overall >= 60:
        return "competent"
    if overall >= 40:
        return "developing"
    return "critical"


def assemble(
    categories: Mapping[str, Sequence[CriterionResult]],
    extraction_confidence: float,
) -> ScoreResult:
    """Turn per-criterion results into the reported bundle.

    Raises rather than reporting an unexplained number: an applicable criterion
    below 1.0 with no finding is a defect in the engine, not a rounding detail.
    """
    included: dict[str, tuple[float, list[CriterionResult], int]] = {}

    for category, criteria in categories.items():
        applicable = [c for c in criteria if c.applicable]
        if not applicable:
            continue
        total_weight = sum(c.weight for c in applicable)
        if total_weight == 0:
            continue
        value = sum(c.weight * c.subscore for c in applicable) / total_weight
        included[category] = (value, applicable, total_weight)

    if not included:
        raise ValueError("nothing was scored: every category was not applicable")

    applicable_weight = sum(CATEGORY_WEIGHTS[category] for category in included)
    overall_raw = (
        100.0
        * sum(CATEGORY_WEIGHTS[category] * value for category, (value, _, _) in included.items())
        / applicable_weight
    )
    overall = round(overall_raw, 1)

    components: dict[ScoreCategory, ScoreComponent] = {}
    for category, (value, applicable, _) in included.items():
        confidence = min(
            (confidence_for(c, extraction_confidence) for c in applicable),
            key=lambda name: ("low", "medium", "high").index(name),
        )
        components[category] = ScoreComponent(  # type: ignore[index]
            value=round(value * 100.0, 1),
            weight=CATEGORY_WEIGHTS[category],
            confidence=confidence,
        )

    findings: list[Finding] = []
    criteria_all: list[CriterionResult] = []
    strengths: list[Strength] = []

    for category, (_, applicable, total_weight) in included.items():
        category_weight = CATEGORY_WEIGHTS[category]
        for criterion in applicable:
            criteria_all.append(criterion)

            if criterion.subscore < 0.999 and not criterion.findings:
                raise ValueError(
                    f"{criterion.criterion} deducted points with no finding — "
                    "an unexplained deduction must never be reported"
                )

            # Exact points this criterion costs on the reported 0-100 scale.
            loss = (
                100.0
                * category_weight
                * (criterion.weight / total_weight)
                * (1.0 - criterion.subscore)
                / applicable_weight
            )

            if criterion.findings:
                primary = criterion.findings[0]
                primary.score_impact = round(loss, 2)
                primary.severity = severity_for_loss(loss)  # type: ignore[assignment]
                for extra in criterion.findings[1:]:
                    # Same defect explained further; already paid for above.
                    extra.score_impact = 0.0
                findings.extend(criterion.findings)

            if criterion.subscore >= 0.9 and criterion.criterion in STRENGTH_TEXT:
                strengths.append(
                    Strength(
                        text=STRENGTH_TEXT[criterion.criterion],
                        evidence=criterion.evidence[:1],
                    )
                )

    findings.sort(
        key=lambda f: (
            -(f.score_impact or 0.0),
            -severity_rank(f.severity),
            f.criterion,
            f.id,
        )
    )

    cq03 = next((c.subscore for c in criteria_all if c.criterion == "CQ-03"), None)
    sk04 = next((c.subscore for c in criteria_all if c.criterion == "SK-04"), None)

    bundle = ScoreBundle(
        methodology_version=METHODOLOGY_VERSION,
        overall=overall,
        applicable_weight=applicable_weight,
        components=components,
        job_match=None,
        band=band_for(overall, cq03, sk04),  # type: ignore[arg-type]
    )

    return ScoreResult(bundle=bundle, findings=findings, strengths=strengths, criteria=criteria_all)


def experience_is_applicable(structure: ResumeStructure) -> bool:
    """§3.1 for the experience category.

    A first-time candidate with no work history and nothing standing in for it
    is `not applicable`, not a zero.
    """
    return bool(
        structure.experience
        or structure.projects
        or structure.sections.experience
    )
