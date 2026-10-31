"""Job-description matching payloads (docs/API.md §2.8).

Three match states are kept distinct on purpose: *absent from the resume*,
*present but not stated*, and *demonstrated with evidence*. Collapsing them is
how a product ends up telling people to add skills they do not have.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SkillStatus = Literal["matched", "partial", "weakly_demonstrated", "absent"]
RequirementStatus = Literal["matched", "partial", "absent", "not_applicable"]

MATCHING_METHODOLOGY_VERSION = "1.0.0"


class JobRequirements(BaseModel):
    """What the description asks for, extracted before any comparison."""

    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    min_years: int | None = None
    degree_level: str | None = None
    responsibilities: list[str] = Field(default_factory=list)


class SkillMatch(BaseModel):
    name: str
    status: SkillStatus
    evidence: list[str] = Field(default_factory=list)
    note: str


class YearsRequirement(BaseModel):
    required: int | None = None
    demonstrated: float | None = None
    status: RequirementStatus = "not_applicable"


class EducationRequirement(BaseModel):
    required: str | None = None
    status: RequirementStatus = "not_applicable"


class ResponsibilityMatch(BaseModel):
    text: str
    status: RequirementStatus


class Gap(BaseModel):
    name: str
    advice: str


class MatchRequirements(BaseModel):
    required_skills: list[SkillMatch] = Field(default_factory=list)
    preferred_skills: list[SkillMatch] = Field(default_factory=list)
    experience_years: YearsRequirement = Field(default_factory=YearsRequirement)
    education: EducationRequirement = Field(default_factory=EducationRequirement)
    responsibilities: list[ResponsibilityMatch] = Field(default_factory=list)


class JobMatch(BaseModel):
    methodology_version: str = MATCHING_METHODOLOGY_VERSION
    estimate: float = Field(ge=0.0, le=100.0)
    requirements: MatchRequirements
    gaps: list[Gap] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


class JobOut(BaseModel):
    id: str
    title: str | None = None
    company: str | None = None
    created_at: datetime
    requirements: JobRequirements | None = None


class MatchOut(BaseModel):
    id: str
    resume_id: str
    job_id: str
    status: str
    methodology_version: str
    created_at: datetime
    completed_at: datetime | None = None
    result: JobMatch | None = None
    failure: dict[str, object] | None = None
