"""Recommendation generation and user decisions.

Generation is idempotent: asking twice returns the same rows rather than
accumulating near-duplicates the user has to clear out.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers.base import NullRewriteProvider, RewriteProvider
from app.core.errors import PotenciaError
from app.intelligence.recommendations import rules
from app.models.analysis import Analysis, Recommendation
from app.models.content import Resume
from app.models.user import User
from app.schemas.recommendations import RecommendationOut
from app.schemas.resume import ResumeStructure
from app.schemas.scores import Finding
from app.services import analysis_service


def get_provider() -> RewriteProvider:
    """No provider is configured yet; deterministic rules cover this phase."""
    return NullRewriteProvider()


def _structure_for(db: Session, analysis: Analysis) -> ResumeStructure:
    resume = db.get(Resume, analysis.resume_id)
    if resume is None or not resume.structure:
        raise PotenciaError("not_found", 404, "Resume not found.")
    return ResumeStructure.model_validate(resume.structure)


def list_for_analysis(db: Session, user: User, analysis_id: uuid.UUID) -> list[Recommendation]:
    analysis = analysis_service.get_analysis(db, user, analysis_id)

    existing = list(
        db.scalars(
            select(Recommendation)
            .where(
                Recommendation.analysis_id == analysis.id,
                Recommendation.user_id == user.id,
            )
            .order_by(Recommendation.created_at)
        )
    )
    if existing:
        return existing

    findings = [Finding.model_validate(item) for item in (analysis.findings or [])]
    if not findings:
        return []

    structure = _structure_for(db, analysis)
    generated = rules.generate(findings, structure)

    rows = [
        Recommendation(
            user_id=user.id,
            analysis_id=analysis.id,
            finding_id=item.finding_id,
            category=item.category,
            priority=item.priority,
            original_text=item.original_text,
            proposed_text=item.proposed_text,
            reason=item.reason,
            remediation=item.remediation,
            requires_user_input=[prompt.model_dump() for prompt in item.requires_user_input],
            confidence=item.confidence,
            state="pending",
            source="rules",
        )
        for item in generated
    ]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def decide(
    db: Session,
    user: User,
    recommendation_id: uuid.UUID,
    *,
    decision: str,
    edited_text: str | None,
) -> Recommendation:
    recommendation = db.scalar(
        select(Recommendation).where(
            Recommendation.id == recommendation_id,
            Recommendation.user_id == user.id,
        )
    )
    if recommendation is None:
        raise PotenciaError("not_found", 404, "Recommendation not found.")

    if decision == "edit" and not edited_text:
        raise PotenciaError(
            "validation_error", 422, "edited_text is required when decision is 'edit'."
        )

    state = {"accept": "accepted", "reject": "rejected", "edit": "edited"}[decision]
    recommendation.state = state
    if decision == "edit" and edited_text:
        recommendation.proposed_text = edited_text
    recommendation.decided_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(recommendation)
    return recommendation


def to_out(recommendation: Recommendation) -> RecommendationOut:
    return RecommendationOut(
        id=str(recommendation.id),
        analysis_id=str(recommendation.analysis_id),
        category=recommendation.category,
        priority=recommendation.priority,
        finding_id=recommendation.finding_id,
        original_text=recommendation.original_text,
        proposed_text=recommendation.proposed_text,
        reason=recommendation.reason,
        remediation=recommendation.remediation,
        requires_user_input=list(recommendation.requires_user_input or []),
        confidence=recommendation.confidence,
        state=recommendation.state,
        decided_at=recommendation.decided_at,
    )
