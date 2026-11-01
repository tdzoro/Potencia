"""Recommendation generation and user decisions.

Generation is idempotent: asking twice returns the same rows rather than
accumulating near-duplicates the user has to clear out. When configured, Google
Gemini provides optional AI-assisted rewrites under strict non-fabrication rules,
while deterministic rules serve as an immediate and reliable fallback.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError, as_completed
import inspect
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers.base import NullRewriteProvider, RewriteProposal, RewriteProvider, RewriteRequest
from app.ai.providers.gemini import GeminiRewriteProvider
from app.core.config import get_settings
from app.core.errors import PotenciaError
from app.intelligence.recommendations import rules
from app.models.analysis import Analysis, Recommendation
from app.models.content import Resume
from app.models.user import User
from app.schemas.recommendations import RecommendationOut
from app.schemas.resume import ResumeStructure
from app.schemas.scores import Finding
from app.services import analysis_service

logger = logging.getLogger(__name__)


def get_provider() -> RewriteProvider:
    """Select the active rewrite provider.

    Returns GeminiRewriteProvider if GEMINI_API_KEY is configured and available;
    otherwise returns NullRewriteProvider.
    """
    settings = get_settings()
    if settings.gemini_api_key:
        provider = GeminiRewriteProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_seconds=settings.gemini_timeout_seconds,
        )
        if provider.available():
            return provider
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

    provider = get_provider()
    provider_available = provider.available()

    # Concurrently pre-fetch AI rewrites for recommendations citing original text (capped to 5)
    proposals_by_finding: dict[str, RewriteProposal] = {}
    if provider_available:
        candidates = [itm for itm in generated if itm.original_text][:5]
        if candidates:
            def _fetch(candidate):
                try:
                    return candidate.finding_id, provider.propose(
                        RewriteRequest(
                            original_text=candidate.original_text,
                            reason=candidate.reason,
                            context=f"Category: {candidate.category}",
                        )
                    )
                except Exception:
                    logger.warning("Failed to generate AI rewrite for recommendation", exc_info=True)
                    return candidate.finding_id, None

            with ThreadPoolExecutor(max_workers=min(5, len(candidates))) as executor:
                future_to_cand = {executor.submit(_fetch, cand): cand for cand in candidates}
                try:
                    for future in as_completed(future_to_cand, timeout=10.0):
                        fid, prop = future.result()
                        if prop and prop.proposed_text:
                            proposals_by_finding[fid] = prop
                except (FutureTimeoutError, TimeoutError):
                    logger.warning("AI rewrite requests exceeded concurrency deadline; degrading to rules")

    rows: list[Recommendation] = []
    for item in generated:
        proposed_text = item.proposed_text
        source = "rules"
        user_inputs = [prompt.model_dump() for prompt in item.requires_user_input]
        confidence = item.confidence

        proposal = proposals_by_finding.get(item.finding_id)
        if proposal and proposal.proposed_text:
            proposed_text = proposal.proposed_text
            source = proposal.provider
            confidence = proposal.confidence
            if proposal.requires_user_input:
                for prompt_dict in proposal.requires_user_input:
                    if prompt_dict not in user_inputs:
                        user_inputs.append(prompt_dict)

        rows.append(
            Recommendation(
                user_id=user.id,
                analysis_id=analysis.id,
                finding_id=item.finding_id,
                category=item.category,
                priority=item.priority,
                original_text=item.original_text,
                proposed_text=proposed_text,
                reason=item.reason,
                remediation=item.remediation,
                requires_user_input=user_inputs,
                confidence=confidence,
                state="pending",
                source=source,
            )
        )

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


def regenerate(
    db: Session,
    user: User,
    recommendation_id: uuid.UUID,
) -> Recommendation:
    """Regenerate a rewrite for an existing recommendation using the active AI provider."""
    recommendation = db.scalar(
        select(Recommendation).where(
            Recommendation.id == recommendation_id,
            Recommendation.user_id == user.id,
        )
    )
    if recommendation is None:
        raise PotenciaError("not_found", 404, "Recommendation not found.")

    if not recommendation.original_text:
        return recommendation

    provider = get_provider()
    if not provider.available():
        raise PotenciaError(
            "dependency_unavailable",
            503,
            "AI rewrite provider is not configured or unavailable.",
        )

    try:
        req = RewriteRequest(
            original_text=recommendation.original_text,
            reason=recommendation.reason,
            context=f"Category: {recommendation.category}",
        )
        propose_sig = inspect.signature(provider.propose)
        if "force_refresh" in propose_sig.parameters:
            proposal = provider.propose(req, force_refresh=True)
        else:
            proposal = provider.propose(req)
    except Exception as exc:
        logger.warning("Error regenerating AI proposal: %s", exc)
        proposal = None

    if proposal and proposal.proposed_text:
        recommendation.proposed_text = proposal.proposed_text
        recommendation.source = proposal.provider
        recommendation.confidence = proposal.confidence
        if proposal.requires_user_input:
            existing = list(recommendation.requires_user_input or [])
            for prompt_dict in proposal.requires_user_input:
                if prompt_dict not in existing:
                    existing.append(prompt_dict)
            recommendation.requires_user_input = existing
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
        source=recommendation.source,
        decided_at=recommendation.decided_at,
    )
