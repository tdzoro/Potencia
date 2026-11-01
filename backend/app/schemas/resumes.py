"""Response schemas for the resume and analysis endpoints (docs/API.md §2.3–§2.8)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.resume import ResumeStructure
from app.schemas.scores import ATSReport, Finding, ScoreBundle, Strength


class ExtractionOut(BaseModel):
    confidence: float
    method: str
    ocr_used: bool
    text_chars: int
    warnings: list[str] = Field(default_factory=list)


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    media_type: str
    size_bytes: int
    page_count: int | None
    status: str
    created_at: datetime
    extraction: ExtractionOut | None = None
    structure: ResumeStructure | None = None
    failure: dict[str, Any] | None = None


class ResumeSummaryOut(BaseModel):
    """List representation: metadata only, without the parsed structure."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    page_count: int | None
    status: str
    created_at: datetime
    extraction: ExtractionOut | None = None


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    resume_id: str
    job_id: str | None = None
    status: str
    methodology_version: str
    created_at: datetime
    completed_at: datetime | None = None
    failure: dict[str, Any] | None = None


class AnalysisDetailOut(AnalysisOut):
    scores: ScoreBundle | None = None
    ats: ATSReport | None = None
    findings: list[Finding] = Field(default_factory=list)
    strengths: list[Strength] = Field(default_factory=list)
    priority_actions: list[str] = Field(default_factory=list)


class AnalysisListOut(BaseModel):
    items: list[AnalysisOut]
    next_cursor: str | None = None
    has_more: bool = False


class ResumeListOut(BaseModel):
    items: list[ResumeSummaryOut]
    next_cursor: str | None = None
    has_more: bool = False


AnalysisStatus = Literal["queued", "running", "completed", "failed"]



class CreateExportRequest(BaseModel):
    analysis_id: uuid.UUID
    kind: Literal["analysis_report", "improved_resume"]
    format: Literal["pdf", "docx"]
    # Omit for "the newest approved version". A resume can hold several named
    # versions, so an export of a specific one must be expressible.
    revision_id: uuid.UUID | None = None


class ExportOut(BaseModel):
    id: str
    analysis_id: str
    revision_id: str | None = None
    kind: str
    format: str
    status: str
    size_bytes: int | None = None
    download_url: str | None = None
    expires_at: datetime | None = None
    failure: dict[str, Any] | None = None
