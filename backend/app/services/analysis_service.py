"""Analysis orchestration: parse result in, scored report out.

The whole run is synchronous. Parsing a two-page PDF and scoring it is
sub-millisecond work locally, so introducing a queue now would add a moving part
without removing any latency. The `status` field stays meaningful for the point
where background execution is genuinely needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import PotenciaError
from app.core.pagination import decode_cursor, encode_cursor
from app.intelligence.scoring.engine import score_resume
from app.models.analysis import Analysis
from app.models.content import Resume
from app.models.user import User
from app.schemas.resume import ResumeStructure
from app.services.resume_service import get_resume


def _priority_actions(findings) -> list[str]:
    """Most expensive problem first — the order a user should work in.

    `score_impact` is the number of points a finding cost (a positive
    magnitude), so descending order puts the biggest loss at the top.
    """
    ranked = sorted(
        (f for f in findings if f.score_impact),
        key=lambda f: f.score_impact,
        reverse=True,
    )
    return [f"{f.title} — {f.remediation}" for f in ranked[:5]]


def create_analysis(db: Session, user: User, resume_id: uuid.UUID) -> Analysis:
    resume: Resume = get_resume(db, user, resume_id)

    if not resume.structure:
        raise PotenciaError(
            "conflict",
            409,
            "This resume has no parsed structure to analyse. Re-upload the document.",
        )

    structure = ResumeStructure.model_validate(resume.structure)
    extraction_confidence = float((resume.extraction or {}).get("confidence", 0.5))

    result = score_resume(structure, extraction_confidence=extraction_confidence)

    analysis = Analysis(
        user_id=user.id,
        resume_id=resume.id,
        job_id=None,
        status="completed",
        methodology_version=result.bundle.methodology_version,
        completed_at=datetime.now(timezone.utc),
    )
    analysis.scores = result.bundle.model_dump(mode="json")
    analysis.ats = result.ats.model_dump(mode="json")
    analysis.findings = [finding.model_dump(mode="json") for finding in result.findings]
    analysis.strengths = [strength.model_dump(mode="json") for strength in result.strengths]
    analysis.priority_actions = _priority_actions(result.findings)

    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def get_analysis(db: Session, user: User, analysis_id: uuid.UUID) -> Analysis:
    analysis = db.scalar(
        select(Analysis).where(Analysis.id == analysis_id, Analysis.user_id == user.id)
    )
    if analysis is None:
        raise PotenciaError("not_found", 404, "Analysis not found.")
    return analysis


def list_analyses(
    db: Session, user: User, limit: int = 20, cursor: str | None = None
) -> tuple[list[Analysis], str | None]:
    """Newest first, keyset-paginated by id (UUIDv7 is time-ordered)."""
    statement = select(Analysis).where(Analysis.user_id == user.id)
    if cursor:
        statement = statement.where(Analysis.id < decode_cursor(cursor))

    rows = list(
        db.scalars(
            statement.order_by(Analysis.id.desc()).limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1].id) if has_more and rows else None
    return rows, next_cursor


def delete_analysis(db: Session, user: User, analysis_id: uuid.UUID) -> None:
    analysis = get_analysis(db, user, analysis_id)
    db.delete(analysis)
    db.commit()
