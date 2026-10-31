"""Analysis endpoints (docs/API.md §3.4).

An analysis is created from an already-parsed resume. The report is the same
object shape whether it is fetched from the list, the detail view or the report
alias — three views of one stored result, never three computations.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.exports import to_api_out
from app.core import idempotency
from app.core.database import get_db
from app.models.analysis import Analysis
from app.models.user import User
from app.schemas.recommendations import RecommendationOut
from app.schemas.resumes import AnalysisDetailOut, AnalysisListOut, AnalysisOut, ExportOut
from app.schemas.scores import ATSReport, Finding, ScoreBundle, Strength
from app.services import analysis_service, export_service, recommendation_service

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
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisDetailOut | Response:
    replayed = idempotency.replay_or_refuse(db, user, request)
    if replayed is not None:
        return replayed

    analysis = analysis_service.create_analysis(db, user, payload.resume_id)
    detail = _to_detail(analysis)
    idempotency.remember(db, user, request, detail, status=201)
    return detail


@router.get("", response_model=AnalysisListOut)
def list_analyses(
    limit: int = 20,
    cursor: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisListOut:
    rows, next_cursor = analysis_service.list_analyses(
        db, user, limit=min(limit, 100), cursor=cursor
    )
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
        ],
        next_cursor=next_cursor,
        has_more=next_cursor is not None,
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


@router.get("/{analysis_id}/exports", response_model=list[ExportOut])
def list_analysis_exports(
    analysis_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ExportOut]:
    return [
        to_api_out(request, record)
        for record in export_service.list_exports(db, user, analysis_id)
    ]


@router.get("/{analysis_id}/recommendations", response_model=list[RecommendationOut])
def list_recommendations(
    analysis_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[RecommendationOut]:
    rows = recommendation_service.list_for_analysis(db, user, analysis_id)
    return [recommendation_service.to_out(row) for row in rows]


@router.delete("/{analysis_id}", status_code=204)
def delete_analysis(
    analysis_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    analysis_service.delete_analysis(db, user, analysis_id)
