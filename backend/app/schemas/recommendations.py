"""Recommendation and revision payloads (docs/API.md §2.9–§2.10)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.resume import ResumeStructure

RecommendationCategory = Literal[
    "summary",
    "experience_bullet",
    "project_description",
    "achievement",
    "skills_organisation",
    "grammar",
    "clarity",
    "relevance",
    "keyword_placement",
    "formatting",
]

RecommendationState = Literal["pending", "accepted", "rejected", "edited"]
RecommendationPriority = Literal["high", "medium", "low"]


class UserInputPrompt(BaseModel):
    field: str
    question: str


class RecommendationOut(BaseModel):
    id: str
    analysis_id: str
    category: RecommendationCategory
    priority: RecommendationPriority
    finding_id: str | None = None
    original_text: str | None = None
    proposed_text: str | None = None
    reason: str
    remediation: str = ""
    requires_user_input: list[UserInputPrompt] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"
    state: RecommendationState = "pending"
    decided_at: datetime | None = None


class DecisionRequest(BaseModel):
    decision: Literal["accept", "reject", "edit"]
    edited_text: str | None = Field(default=None, max_length=2000)


class RevisionOut(BaseModel):
    id: str
    resume_id: str
    parent_id: str | None = None
    label: str | None = None
    applied_recommendations: list[str] = Field(default_factory=list)
    content: ResumeStructure | None = None
    created_at: datetime


class CreateRevisionRequest(BaseModel):
    """A user-approved version of the parsed resume.

    The client sends the whole structure back, so a revision is a complete,
    reviewable artefact rather than a diff that cannot be interpreted alone.
    """

    content: ResumeStructure
    # Typed as a UUID so a malformed id is a 422 from the framework, not a 500
    # from `uuid.UUID(...)` inside the handler.
    parent_id: uuid.UUID | None = None
    label: str | None = Field(default=None, max_length=80)
    applied_recommendation_ids: list[str] = Field(default_factory=list)


class RevisionChange(BaseModel):
    """One field that differs between two versions."""

    field: str
    before: str | None = None
    after: str | None = None


class RevisionCompareOut(BaseModel):
    resume_id: str
    from_revision: str
    to_revision: str
    from_label: str | None = None
    to_label: str | None = None
    changes: list[RevisionChange] = Field(default_factory=list)
