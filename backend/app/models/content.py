"""Resume, revision and job-description models.

Parsed documents and extracted structure are stored as JSON rather than dozens
of normalised columns: the structure is produced by one engine and consumed
whole, never queried field-by-field. Relations that *are* queried — ownership,
timestamps, status — stay as real columns.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Resume(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "resumes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    # Locator for the object store, never a public URL (docs/API.md §2.11).
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)

    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")

    # {confidence, method, ocr_used, text_chars, warnings}
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # ResumeStructure (docs/API.md §2.4)
    structure: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    failure: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    revisions: Mapped[list["ResumeRevision"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan", order_by="ResumeRevision.created_at"
    )

    __table_args__ = (
        # Every list query is scoped by owner and ordered by recency.
        Index("ix_resumes_user_created", "user_id", "created_at"),
    )


class ResumeRevision(Base, UUIDPrimaryKeyMixin):
    """One immutable edit of a resume.

    Revision 0 is the untouched parse. Later revisions point at their parent, so
    the history is a tree rather than a guess, and the original is never
    overwritten.
    """

    __tablename__ = "resume_revisions"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("resume_revisions.id", ondelete="SET NULL"), nullable=True
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    applied_recommendations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # A user-chosen name ("Backend", "Data engineer") so a resume can hold
    # several versions side by side without duplicating the document.
    label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    resume: Mapped[Resume] = relationship(back_populates="revisions")

    __table_args__ = (Index("ix_resume_revisions_user_resume", "user_id", "resume_id"),)


class Job(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A job description the user pasted.

    `title` and `company` are the user's own labels for their list; matching uses
    `description` only, so a label can never be mistaken for a hiring signal.
    """

    __tablename__ = "jobs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Extracted requirements, cached so matching does not re-parse each run.
    extracted: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (Index("ix_jobs_user_created", "user_id", "created_at"),)
