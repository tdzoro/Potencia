"""Resume revision history.

Revision 0 is the untouched parse, written when the document is ingested. Every
later revision is a complete structure that points at its parent, so the history
is a tree rather than a diff that cannot be read on its own. The original is
never overwritten — an edit is a new node.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import PotenciaError
from app.models.content import ResumeRevision
from app.models.user import User
from app.schemas.resume import ResumeStructure
from app.services.resume_service import get_resume


def create_revision(
    db: Session,
    user: User,
    resume_id: uuid.UUID,
    *,
    content: ResumeStructure,
    parent_id: uuid.UUID | None,
    applied_recommendation_ids: list[str],
) -> ResumeRevision:
    resume = get_resume(db, user, resume_id)

    if parent_id is not None:
        parent = db.scalar(
            select(ResumeRevision).where(
                ResumeRevision.id == parent_id,
                ResumeRevision.resume_id == resume.id,
                ResumeRevision.user_id == user.id,
            )
        )
        if parent is None:
            raise PotenciaError("not_found", 404, "Parent revision not found.")

    revision = ResumeRevision(
        resume_id=resume.id,
        user_id=user.id,
        parent_id=parent_id,
        content=content.model_dump(mode="json"),
        applied_recommendations=applied_recommendation_ids,
        created_at=datetime.now(timezone.utc),
    )
    db.add(revision)
    db.commit()
    db.refresh(revision)
    return revision


def list_revisions(db: Session, user: User, resume_id: uuid.UUID) -> list[ResumeRevision]:
    resume = get_resume(db, user, resume_id)
    return list(
        db.scalars(
            select(ResumeRevision)
            .where(ResumeRevision.resume_id == resume.id, ResumeRevision.user_id == user.id)
            .order_by(ResumeRevision.created_at)
        )
    )


def create_initial_revision(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID, content: ResumeStructure) -> ResumeRevision:
    """Revision 0: the parse exactly as produced, never edited in place."""
    revision = ResumeRevision(
        resume_id=resume_id,
        user_id=user_id,
        parent_id=None,
        content=content.model_dump(mode="json"),
        applied_recommendations=[],
        created_at=datetime.now(timezone.utc),
    )
    db.add(revision)
    return revision
