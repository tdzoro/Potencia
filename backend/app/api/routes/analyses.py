"""Analysis endpoints (docs/API.md §3.4).

An analysis is created from an already-parsed resume. The report is the same
object shape whether it is fetched from the list, the detail view or the report
alias — three views of one stored result, never three computations.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.analysis import Analysis
from app.models.user import User
from app.schemas.resumes import AnalysisDetailOut, AnalysisListOut, AnalysisOut
from app.schemas.scores import ATSReport, Finding, ScoreBundle, Strength
from app.services import analysis_service

router = APIRouter(prefix="/analyses", tags=["analyses"])


class CreateAnalysisRequest(BaseModel):
    resume_id: uuid.UUID
    job_id: uuid.UUID | None = None


def _to_detail(analysis: Analysis) -> AnalysisDetailOut:
    return AnalysisDetailOut(
        id=str(analysis.id),
        resume_id=str(analysis.resume_id),
        job_id=str(analysis.job_id) if analysis.job_id else None,
        status=analysis.status,
        methodology_version=analysis.methodology_version,
        created_at=analysis.created_at,
        completed_at=analysis.completed_at,
        failure=analysis.failure,
        scores=ScoreBundle.model_validate(analysis.scores) if analysis.scores else None,
        ats=ATSReport.model_validate(analysis.ats) if analysis.ats else None,
        findings=[Finding.model_validate(item) for item in (analysis.findings or [])],
        strengths=[Strength.model_validate(item) for item in (analysis.strengths or [])],
        priority_actions=list(analysis.priority_actions or []),
    )


@router.post("", status_code=201, response_model=AnalysisDetailOut)
def create_analysis(
    payload: CreateAnalysisRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisDetailOut:
    analysis = analysis_service.create_analysis(db, user, payload.resume_id)
    return _to_detail(analysis)


@router.get("", response_model=AnalysisListOut)
def list_analyses(
    limit: int = 20, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> AnalysisListOut:
    rows = analysis_service.list_analyses(db, user, limit=min(limit, 100))
    return AnalysisListOut(
        items=[
            AnalysisOut(
                id=str(analysis.id),
                resume_id=str(analysis.resume_id),
                job_id=str(analysis.job_id) if analysis.job_id else None,
                status=analysis.status,
                methodology_version=analysis.methodology_version,
                created_at=analysis.created_at,
                completed_at=analysis.completed_at,
                failure=analysis.failure,
            )
            for analysis in rows
        ]
    )


@router.get("/{analysis_id}", response_model=AnalysisDetailOut)
def read_analysis(
    analysis_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> AnalysisDetailOut:
    return _to_detail(analysis_service.get_analysis(db, user, analysis_id))


@router.get("/{analysis_id}/report", response_model=AnalysisDetailOut)
def read_report(
    analysis_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> AnalysisDetailOut:
    return _to_detail(analysis_service.get_analysis(db, user, analysis_id))


@router.delete("/{analysis_id}", status_code=204)
def delete_analysis(
    analysis_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    analysis_service.delete_analysis(db, user, analysis_id)
