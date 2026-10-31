"""Deterministic recommendation generation.

Every proposal here is derived from a finding that already cites resume text, so
nothing is invented. Where a better sentence would need a fact the resume does
not contain — a number, a scale, a technology — the recommendation asks for it
instead of supplying one.
"""

from __future__ import annotations

import re
import uuid

from app.schemas.recommendations import RecommendationCategory, RecommendationOut
from app.schemas.resume import ResumeStructure
from app.schemas.scores import Finding

# Conservative, meaning-preserving swaps only. Anything that would change what
# the sentence claims is excluded on purpose.
_WEAK_VERBS = {
    "worked on": "Delivered",
    "worked with": "Collaborated with",
    "helped": "Supported",
    "assisted with": "Supported",
    "responsible for": "Owned",
    "involved in": "Contributed to",
    "participated in": "Contributed to",
    "handled": "Managed",
}

_CATEGORY_BY_CRITERION: dict[str, RecommendationCategory] = {
    "CQ-01": "summary",
    "CQ-02": "experience_bullet",
    "CQ-03": "experience_bullet",
    "CQ-04": "clarity",
    "CQ-05": "clarity",
    "EX-01": "experience_bullet",
    "EX-02": "experience_bullet",
    "EX-03": "experience_bullet",
    "EX-04": "experience_bullet",
    "EX-05": "relevance",
    "SK-01": "skills_organisation",
    "SK-02": "skills_organisation",
    "SK-03": "skills_organisation",
    "SK-04": "skills_organisation",
    "SK-05": "skills_organisation",
    "ST-01": "formatting",
    "ST-02": "formatting",
    "ST-03": "formatting",
    "ST-04": "formatting",
    "ST-05": "formatting",
    "AT-01": "formatting",
    "AT-02": "formatting",
    "AT-03": "formatting",
    "AT-04": "formatting",
    "AT-05": "formatting",
    "LR-01": "grammar",
    "LR-02": "grammar",
    "LR-03": "clarity",
    "LR-04": "clarity",
    "LR-05": "clarity",
}

_PRIORITY_BY_SEVERITY = {
    "critical": "high",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "info": "low",
}


def _replacement_for(text: str) -> str | None:
    """Swap a weak opener for a stronger one, or return None if not applicable."""
    lowered = text.lower()
    for weak, strong in _WEAK_VERBS.items():
        if lowered.startswith(weak):
            remainder = text[len(weak) :].lstrip()
            return f"{strong} {remainder}".strip()
    return None


def _prompts_for(finding: Finding) -> list[dict[str, str]]:
    if finding.criterion == "CQ-03":
        return [
            {
                "field": "metric",
                "question": (
                    "What scale did this work operate at — records, requests per day, "
                    "users, revenue, or time saved? Give the real figure."
                ),
            }
        ]
    if finding.criterion == "SK-04":
        return [
            {
                "field": "evidence",
                "question": (
                    "Which role or project used this skill? Add it there, or remove the "
                    "claim if you have not used it."
                ),
            }
        ]
    if finding.criterion in {"EX-02", "AT-04"}:
        return [
            {
                "field": "dates",
                "question": "What are the exact start and end months for this role?",
            }
        ]
    if finding.criterion == "CQ-01":
        return [
            {
                "field": "summary",
                "question": (
                    "What role are you targeting, and what single result best shows you "
                    "can do it?"
                ),
            }
        ]
    return []


def generate(findings: list[Finding], structure: ResumeStructure) -> list[RecommendationOut]:
    """Turn findings into reviewable, user-controlled proposals."""
    recommendations: list[RecommendationOut] = []
    seen: set[tuple[str, str]] = set()

    for finding in findings:
        original = finding.evidence[0].text if finding.evidence else None

        if original is not None:
            key = (finding.criterion, original)
            if key in seen:
                continue
            seen.add(key)

        proposed = _replacement_for(original) if original else None
        if proposed is not None and proposed == original:
            proposed = None

        recommendations.append(
            RecommendationOut(
                id=f"r_{uuid.uuid4().hex[:16]}",
                analysis_id="",
                category=_CATEGORY_BY_CRITERION.get(finding.criterion, "clarity"),
                priority=_PRIORITY_BY_SEVERITY.get(finding.severity, "medium"),
                finding_id=finding.id,
                original_text=original,
                proposed_text=proposed,
                reason=finding.explanation,
                remediation=finding.remediation,
                requires_user_input=_prompts_for(finding),
                confidence="high" if proposed or finding.evidence else "medium",
                state="pending",
            )
        )

    return recommendations


def summarise_skill_gaps(structure: ResumeStructure) -> str | None:
    """A single sentence naming unsubstantiated claims, or None."""
    claimed = {skill.lower() for skill in structure.skills.explicit}
    body = structure.substantiated_text().lower()
    unsupported = sorted(skill for skill in claimed if skill not in body)
    if not unsupported:
        return None
    listed = re.sub(r"\s+", " ", ", ".join(unsupported))
    return f"Claimed but never demonstrated: {listed}."
