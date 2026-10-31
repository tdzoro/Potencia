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
    label: str | None = None,
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
        label=(label.strip()[:80] if label and label.strip() else None),
        created_at=datetime.now(timezone.utc),
    )
    db.add(revision)
    db.commit()
    db.refresh(revision)
    return revision


def _flatten(structure: ResumeStructure) -> dict[str, str]:
    """A comparable view of the fields a user can actually edit.

    Flattening to `field -> text` keeps the diff readable and keeps the
    comparison honest: only fields the studio can change are compared.
    """
    fields: dict[str, str] = {}
    fields["summary"] = structure.summary.text or ""
    fields["skills"] = ", ".join(structure.skills.explicit)
    for role_index, role in enumerate(structure.experience):
        for bullet_index, bullet in enumerate(role.bullets):
            fields[f"experience[{role_index}].bullet[{bullet_index}]"] = bullet.text
    return fields


def compare_revisions(
    db: Session,
    user: User,
    resume_id: uuid.UUID,
    *,
    from_revision_id: uuid.UUID,
    to_revision_id: uuid.UUID,
) -> tuple[ResumeRevision, ResumeRevision, list[dict[str, str | None]]]:
    """Field-level diff between two owned versions of the same resume."""
    resume = get_resume(db, user, resume_id)
    rows = {
        row.id: row
        for row in db.scalars(
            select(ResumeRevision).where(
                ResumeRevision.resume_id == resume.id,
                ResumeRevision.user_id == user.id,
                ResumeRevision.id.in_([from_revision_id, to_revision_id]),
            )
        )
    }
    if from_revision_id not in rows or to_revision_id not in rows:
        raise PotenciaError("not_found", 404, "Revision not found.")

    before = rows[from_revision_id]
    after = rows[to_revision_id]
    left = _flatten(ResumeStructure.model_validate(before.content))
    right = _flatten(ResumeStructure.model_validate(after.content))

    changes: list[dict[str, str | None]] = []
    for field in list(dict.fromkeys([*left, *right])):
        old, new = left.get(field, ""), right.get(field, "")
        if old != new:
            changes.append({"field": field, "before": old or None, "after": new or None})
    return before, after, changes


def list_revisions(db: Session, user: User, resume_id: uuid.UUID) -> list[ResumeRevision]:
    resume = get_resume(db, user, resume_id)
    return list(
        db.scalars(
            select(ResumeRevision)
            .where(ResumeRevision.resume_id == resume.id, ResumeRevision.user_id == user.id)
            .order_by(ResumeRevision.created_at, ResumeRevision.id)
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
