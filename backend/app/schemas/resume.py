"""The structured resume representation (docs/API.md §2.4).

This is the contract between the parser, the scoring engine, the ATS analyzer,
job matching and the frontend. A field here that a downstream stage cannot
trace back to source text is a bug: every value is either extracted or absent,
never guessed.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DatePrecision = Literal["day", "month", "year", "present", "unknown"]
SectionKind = Literal[
    "summary",
    "experience",
    "education",
    "skills",
    "projects",
    "certifications",
    "achievements",
    "leadership",
    "contact",
    "other",
]
Confidence = Literal["low", "medium", "high"]


class Bullet(BaseModel):
    """One bullet point, with the character span it occupied in the source."""

    text: str
    span: tuple[int, int] | None = None


class Contact(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    links: list[str] = Field(default_factory=list)


class SummaryBlock(BaseModel):
    text: str | None = None
    present: bool = False


class ExperienceEntry(BaseModel):
    title: str | None = None
    organisation: str | None = None
    start: str | None = None
    end: str | None = None
    date_precision: DatePrecision = "unknown"
    bullets: list[Bullet] = Field(default_factory=list)


class EducationEntry(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field: str | None = None
    start: str | None = None
    end: str | None = None
    details: list[str] = Field(default_factory=list)


class ProjectEntry(BaseModel):
    name: str | None = None
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    bullets: list[Bullet] = Field(default_factory=list)


class CertificationEntry(BaseModel):
    name: str
    issuer: str | None = None
    date: str | None = None


class InferredSkill(BaseModel):
    """A skill the resume implies but does not state outright.

    Kept separate from explicitly claimed skills, because "appears in a bullet"
    and "the candidate says they have this" are different facts.
    """

    name: str
    basis: str


class SkillSet(BaseModel):
    explicit: list[str] = Field(default_factory=list)
    inferred: list[InferredSkill] = Field(default_factory=list)

    @property
    def all_names(self) -> list[str]:
        return [*self.explicit, *(skill.name for skill in self.inferred)]


class Uncertainty(BaseModel):
    """A field that could not be determined. Never filled with a plausible guess."""

    field: str
    reason: str


class SectionPresence(BaseModel):
    """Which canonical sections the document actually contains.

    Used by scoring to distinguish `not applicable` from `missing`
    (SCORING_METHODOLOGY.md §3).
    """

    contact: bool = False
    summary: bool = False
    experience: bool = False
    education: bool = False
    skills: bool = False
    projects: bool = False
    certifications: bool = False
    achievements: bool = False
    leadership: bool = False


class ResumeStructure(BaseModel):
    contact: Contact = Field(default_factory=Contact)
    summary: SummaryBlock = Field(default_factory=SummaryBlock)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    certifications: list[CertificationEntry] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    leadership: list[str] = Field(default_factory=list)
    skills: SkillSet = Field(default_factory=SkillSet)
    sections: SectionPresence = Field(default_factory=SectionPresence)
    uncertain: list[Uncertainty] = Field(default_factory=list)

    word_count: int = 0
    bullet_count: int = 0
    page_count: int = 1
    has_dates: bool = False
    date_formats: list[str] = Field(default_factory=list)
    reading_order_risk: Literal["none", "low", "medium", "high"] = "none"

    def all_bullets(self) -> list[Bullet]:
        bullets: list[Bullet] = []
        for role in self.experience:
            bullets.extend(role.bullets)
        for project in self.projects:
            bullets.extend(project.bullets)
        return bullets

    def experience_text(self) -> str:
        """Role text used for cross-checks that specifically measure experience."""
        parts: list[str] = []
        for role in self.experience:
            parts.append(" ".join(filter(None, [role.title, role.organisation])))
            parts.extend(b.text for b in role.bullets)
        return " ".join(parts)

    def skill_evidence_text(self) -> str:
        """Evidence outside the summary and skills list for explicitly claimed skills."""
        parts = [self.experience_text()]
        for project in self.projects:
            parts.append(" ".join(filter(None, [project.name, project.description])))
            parts.extend(project.technologies)
            parts.extend(b.text for b in project.bullets)
        parts.extend(c.name for c in self.certifications)
        parts.extend(self.achievements)
        parts.extend(self.leadership)
        return " ".join(parts)

    def substantiated_text(self) -> str:
        """All descriptive text except the skills list, including the summary."""
        parts: list[str] = []
        if self.summary.text:
            parts.append(self.summary.text)
        for role in self.experience:
            parts.append(" ".join(filter(None, [role.title, role.organisation])))
            parts.extend(b.text for b in role.bullets)
        for project in self.projects:
            parts.append(" ".join(filter(None, [project.name, project.description])))
            parts.extend(b.text for b in project.bullets)
        parts.extend(c.name for c in self.certifications)
        parts.extend(self.achievements)
        parts.extend(self.leadership)
        return " ".join(parts)


class ExtractionResult(BaseModel):
    """What the document layer produces, before structure is inferred."""

    text: str
    page_count: int
    method: Literal["text_layer", "ocr", "partial", "failed"]
    confidence: float = Field(ge=0.0, le=1.0)
    ocr_used: bool = False
    warnings: list[str] = Field(default_factory=list)


class ParsedResume(BaseModel):
    structure: ResumeStructure
    extraction: ExtractionResult
