"""Recommendation decisions and AI rewrites (docs/API.md §3.7)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.recommendations import DecisionRequest, RecommendationOut
from app.services import recommendation_service

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("/{recommendation_id}/decision", response_model=RecommendationOut)
def decide(
    recommendation_id: uuid.UUID,
    payload: DecisionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecommendationOut:
    recommendation = recommendation_service.decide(
        db,
        user,
        recommendation_id,
        decision=payload.decision,
        edited_text=payload.edited_text,
    )
    return recommendation_service.to_out(recommendation)


@router.post("/{recommendation_id}/regenerate", response_model=RecommendationOut)
def regenerate(
    recommendation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecommendationOut:
    """Regenerate an AI rewrite suggestion for this recommendation using Gemini."""
    recommendation = recommendation_service.regenerate(
        db,
        user,
        recommendation_id,
    )
    return recommendation_service.to_out(recommendation)
