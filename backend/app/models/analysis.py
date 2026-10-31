"""Analysis results, job matches, recommendations and exports.

Every row is owned by a `user_id`. Ownership is enforced in the query layer, so
a request for another user's row returns `404` rather than `403` — whether a
resource exists is itself private information (docs/API.md §1.3).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Analysis(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "analyses"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    resume_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    # Recorded per analysis so a stored report never silently changes meaning
    # when the weights are recalibrated (SCORING_METHODOLOGY.md §8).
    methodology_version: Mapped[str] = mapped_column(String(20), nullable=False)

    scores: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ats: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    findings: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    strengths: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    priority_actions: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    failure: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_analyses_user_created", "user_id", "created_at"),
        Index("ix_analyses_resume", "resume_id"),
    )


class Match(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "matches"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    resume_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    methodology_version: Mapped[str] = mapped_column(String(20), nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    failure: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_matches_user_created", "user_id", "created_at"),)


class Recommendation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "recommendations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    finding_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    category: Mapped[str] = mapped_column(String(40), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # The concrete next step. Without it a card can say what is wrong and still
    # leave the user with nothing to do.
    remediation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Questions the model must ask instead of inventing a metric (§2.9).
    requires_user_input: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    source: Mapped[str] = mapped_column(String(12), nullable=False, default="rules")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_recommendations_analysis", "analysis_id", "user_id"),)


class Export(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "exports"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    format: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (Index("ix_exports_user_created", "user_id", "created_at"),)
