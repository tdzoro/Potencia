"""Job-description endpoints (docs/API.md §3.5)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.content import Job
from app.models.user import User
from app.schemas.matching import JobOut, JobRequirements
from app.services import matching_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


class CreateJobRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    description: str = Field(min_length=20, max_length=40_000)


def _to_out(job: Job) -> JobOut:
    return JobOut(
        id=str(job.id),
        title=job.title,
        company=job.company,
        created_at=job.created_at,
        requirements=JobRequirements.model_validate(job.extracted) if job.extracted else None,
    )


@router.post("", status_code=201, response_model=JobOut)
def create_job(
    payload: CreateJobRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobOut:
    job = matching_service.create_job(
        db,
        user,
        title=payload.title,
        company=payload.company,
        description=payload.description,
    )
    return _to_out(job)


@router.get("", response_model=list[JobOut])
def list_jobs(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[JobOut]:
    return [_to_out(job) for job in matching_service.list_jobs(db, user)]


@router.get("/{job_id}", response_model=JobOut)
def read_job(
    job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> JobOut:
    return _to_out(matching_service.get_job(db, user, job_id))


@router.delete("/{job_id}", status_code=204)
def delete_job(
    job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    matching_service.delete_job(db, user, job_id)
