"""Job descriptions and resume matching."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import PotenciaError
from app.intelligence.matching.engine import match_resume
from app.intelligence.matching.requirements import extract_requirements
from app.models.analysis import Match
from app.models.content import Job, Resume
from app.models.user import User
from app.schemas.matching import JobRequirements, MATCHING_METHODOLOGY_VERSION
from app.schemas.resume import ResumeStructure
from app.services.resume_service import get_resume


def create_job(
    db: Session,
    user: User,
    *,
    title: str | None,
    company: str | None,
    description: str,
) -> Job:
    requirements = extract_requirements(description)
    job = Job(
        user_id=user.id,
        title=title[:200] if title else None,
        company=company[:200] if company else None,
        description=description,
        extracted=requirements.model_dump(mode="json"),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, user: User, job_id: uuid.UUID) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id, Job.user_id == user.id))
    if job is None:
        raise PotenciaError("not_found", 404, "Job description not found.")
    return job


def list_jobs(db: Session, user: User, limit: int = 20) -> list[Job]:
    return list(
        db.scalars(
            select(Job)
            .where(Job.user_id == user.id)
            .order_by(Job.created_at.desc())
            .limit(limit)
        )
    )


def delete_job(db: Session, user: User, job_id: uuid.UUID) -> None:
    job = get_job(db, user, job_id)
    db.delete(job)
    db.commit()


def create_match(db: Session, user: User, resume_id: uuid.UUID, job_id: uuid.UUID) -> Match:
    resume: Resume = get_resume(db, user, resume_id)
    job: Job = get_job(db, user, job_id)

    if not resume.structure:
        raise PotenciaError(
            "conflict", 409, "This resume has no parsed structure to match against."
        )

    structure = ResumeStructure.model_validate(resume.structure)
    requirements = JobRequirements.model_validate(job.extracted or {})

    result = match_resume(structure, requirements)

    match = Match(
        user_id=user.id,
        resume_id=resume.id,
        job_id=job.id,
        status="completed",
        methodology_version=MATCHING_METHODOLOGY_VERSION,
        completed_at=datetime.now(timezone.utc),
    )
    match.result = result.model_dump(mode="json")

    db.add(match)
    db.commit()
    db.refresh(match)
    return match


def get_match(db: Session, user: User, match_id: uuid.UUID) -> Match:
    match = db.scalar(select(Match).where(Match.id == match_id, Match.user_id == user.id))
    if match is None:
        raise PotenciaError("not_found", 404, "Match not found.")
    return match
