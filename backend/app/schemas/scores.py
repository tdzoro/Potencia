"""Scoring, findings and ATS payloads (docs/API.md §2.5–§2.7).

`score_impact` exists so that the findings shown to a user reconcile with the
number at the top of the report. If they do not sum, the report is wrong and
must not ship — that reconciliation is a test, not an aspiration.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["critical", "high", "medium", "low", "info"]
Confidence = Literal["low", "medium", "high"]
CriterionStatus = Literal["passed", "warn", "failed", "not_applicable"]

ScoreCategory = Literal[
    "content_quality",
    "experience",
    "skills",
    "structure",
    "ats_compatibility",
    "language_readability",
]

CATEGORY_WEIGHTS: dict[str, int] = {
    "content_quality": 25,
    "experience": 20,
    "skills": 15,
    "structure": 15,
    "ats_compatibility": 15,
    "language_readability": 10,
}

METHODOLOGY_VERSION = "1.1.0"


class Evidence(BaseModel):
    """A verbatim location in the resume. Paraphrase is not evidence."""

    section: str
    text: str
    page: int | None = None


class Finding(BaseModel):
    id: str
    category: ScoreCategory
    criterion: str
    severity: Severity
    title: str
    evidence: list[Evidence] = Field(default_factory=list)
    explanation: str
    remediation: str
    score_impact: float | None = None
    source: Literal["rules", "nlp", "llm"] = "rules"


class ScoreComponent(BaseModel):
    value: float = Field(ge=0.0, le=100.0)
    weight: int = Field(gt=0)
    confidence: Confidence = "medium"


class ScoreBundle(BaseModel):
    methodology_version: str = METHODOLOGY_VERSION
    overall: float = Field(ge=0.0, le=100.0)
    applicable_weight: int
    components: dict[ScoreCategory, ScoreComponent]
    job_match: float | None = None
    band: Literal["critical", "developing", "competent", "strong", "exceptional"]


class ATSCheck(BaseModel):
    id: str
    label: str
    status: Literal["pass", "warn", "fail"]
    severity: Severity
    evidence: list[Evidence] = Field(default_factory=list)
    explanation: str
    remediation: str


class ATSReport(BaseModel):
    estimate: float = Field(ge=0.0, le=100.0)
    disclaimer: str = (
        "ATS compatibility estimate. Not a prediction of screening outcomes."
    )
    checks: list[ATSCheck] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


class CriterionResult(BaseModel):
    """Internal per-criterion outcome, before it becomes a Finding.

    `applicable=False` is how a criterion leaves the denominator instead of
    scoring zero (SCORING_METHODOLOGY.md §3).
    """

    criterion: str
    category: ScoreCategory
    weight: int
    property: str
    applicable: bool = True
    subscore: float = Field(ge=0.0, le=1.0, default=0.0)
    detail: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


class Strength(BaseModel):
    text: str
    evidence: list[Evidence] = Field(default_factory=list)
