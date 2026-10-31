"""Match endpoints (docs/API.md §3.6)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.analysis import Match
from app.models.user import User
from app.schemas.matching import JobMatch, MatchOut
from app.services import matching_service

router = APIRouter(prefix="/matches", tags=["matches"])


class CreateMatchRequest(BaseModel):
    resume_id: uuid.UUID
    job_id: uuid.UUID


def _to_out(match: Match) -> MatchOut:
    return MatchOut(
        id=str(match.id),
        resume_id=str(match.resume_id),
        job_id=str(match.job_id),
        status=match.status,
        methodology_version=match.methodology_version,
        created_at=match.created_at,
        completed_at=match.completed_at,
        result=JobMatch.model_validate(match.result) if match.result else None,
        failure=match.failure,
    )


@router.post("", status_code=201, response_model=MatchOut)
def create_match(
    payload: CreateMatchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MatchOut:
    return _to_out(
        matching_service.create_match(db, user, payload.resume_id, payload.job_id)
    )


@router.get("/{match_id}", response_model=MatchOut)
def read_match(
    match_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> MatchOut:
    return _to_out(matching_service.get_match(db, user, match_id))
