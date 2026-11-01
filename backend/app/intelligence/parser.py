"""Resume structure extraction.

The parser is conservative by design. Every value it returns is either present in
the text or `None`; anything it cannot resolve is recorded in `uncertain` rather
than filled with a plausible guess. A wrong employer or a wrong date silently
corrupts a score the user is expected to act on, which is worse than an honest
gap.

`SectionPresence` records whether a *heading* was found, not whether content was
parsed. Scoring uses that distinction to separate "missing" from "not applicable"
(SCORING_METHODOLOGY.md §3).
"""

from __future__ import annotations

import re

from app.intelligence.normalization import (
    collapse_spaces,
    find_date_tokens,
    is_bullet_line,
    normalize_whitespace,
    parse_date_range,
    split_skill_list,
    strip_bullet_marker,
    strip_date_text,
    word_count,
)
from app.intelligence.taxonomy import canonicalise, find_skills
from app.schemas.resume import (
    Bullet,
    CertificationEntry,
    Contact,
    EducationEntry,
    ExperienceEntry,
    ExtractionResult,
    InferredSkill,
    ProjectEntry,
    ResumeStructure,
    SectionPresence,
    SkillSet,
    SummaryBlock,
    Uncertainty,
)

# --- Section headings -------------------------------------------------------

_SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "summary": (
        "summary",
        "professional summary",
        "profile",
        "professional profile",
        "objective",
        "career objective",
        "about",
        "about me",
        "executive summary",
        "career summary",
    ),
    "experience": (
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "employment history",
        "work history",
        "career history",
        "relevant experience",
        "internship",
        "internships",
        "professional background",
        "industry experience",
    ),
    "education": (
        "education",
        "academic background",
        "qualifications",
        "academic qualifications",
        "education and training",
        "academic details",
    ),
    "skills": (
        "skills",
        "technical skills",
        "core skills",
        "key skills",
        "technical proficiencies",
        "competencies",
        "core competencies",
        "technologies",
        "tech stack",
        "tools and technologies",
        "expertise",
        "technical expertise",
    ),
    "projects": (
        "projects",
        "personal projects",
        "academic projects",
        "selected projects",
        "side projects",
        "key projects",
    ),
    "certifications": (
        "certifications",
        "certificates",
        "licenses",
        "licenses and certifications",
        "professional certifications",
        "certifications and licenses",
    ),
    "achievements": (
        "achievements",
        "awards",
        "honors",
        "honours",
        "awards and achievements",
        "accomplishments",
        "key achievements",
    ),
    "leadership": (
        "leadership",
        "leadership experience",
        "extracurricular",
        "extracurricular activities",
        "volunteer",
        "volunteering",
        "volunteer experience",
        "positions of responsibility",
        "activities",
        "community involvement",
    ),
}

_HEADING_LOOKUP: dict[str, str] = {}
for _kind, _keywords in _SECTION_KEYWORDS.items():
    for _keyword in _keywords:
        _HEADING_LOOKUP[_keyword] = _kind

# Longest keyword first, computed once at import. Re-sorting this on every line
# was the single largest cost in the parser: a profile of one document showed it
# at roughly 40% of parse time, for an ordering that never changes.
_HEADING_PREFIXES: tuple[tuple[str, str], ...] = tuple(
    sorted(_HEADING_LOOKUP.items(), key=lambda item: len(item[0]), reverse=True)
)

# ...and bucketed by its first word, so classifying a line tests the handful of
# headings that could possibly match instead of all ninety. Buckets keep the
# longest-first order, which is what lets "React Native" beat "React".
_heading_buckets: dict[str, list[tuple[str, str]]] = {}
for _keyword, _kind in _HEADING_PREFIXES:
    _heading_buckets.setdefault(_keyword.split(" ", 1)[0], []).append((_keyword, _kind))
_HEADING_BY_FIRST_WORD: dict[str, tuple[tuple[str, str], ...]] = {
    _word: tuple(_entries) for _word, _entries in _heading_buckets.items()
}

_WHITESPACE_RE = re.compile(r"\s+")

# Words that may follow a heading keyword without making it prose.
_HEADING_MODIFIERS: frozenset[str] = frozenset(
    {
        "and",
        "history",
        "summary",
        "details",
        "internship",
        "internships",
        "activities",
        "activity",
        "certifications",
        "certificates",
        "licenses",
        "achievements",
        "awards",
        "honors",
        "honours",
        "training",
        "professional",
        "relevant",
        "academic",
        "technical",
        "core",
        "key",
        "work",
        "volunteer",
        "extracurricular",
        "positions",
        "responsibility",
        "proficiencies",
        "competencies",
        "background",
        "experience",
        "all",
        "of",
    }
)


def classify_heading(line: str) -> str | None:
    """Return a section kind if the line reads as a section heading."""
    text = collapse_spaces(strip_bullet_marker(line)).strip(":;|•–—- ")
    if not text or len(text) > 60:
        return None

    key = _WHITESPACE_RE.sub(" ", text.lower()).strip(" :;|•–—-")
    if key in _HEADING_LOOKUP:
        return _HEADING_LOOKUP[key]

    # "WORK EXPERIENCE & INTERNSHIPS" — a known heading plus recognised
    # modifiers. Anything else after the keyword is prose, not a heading:
    # "Experience with Python and Django" must not open a section.
    for keyword, kind in _HEADING_BY_FIRST_WORD.get(key.split(" ", 1)[0], ()):
        if not key.startswith(keyword):
            continue
        suffix = key[len(keyword) :].replace("&", " and ")
        words = {word for word in re.split(r"[\s-]+", suffix) if word}
        if words and words <= _HEADING_MODIFIERS and len(key) <= len(keyword) + 40:
            return kind

    return None


# --- Contact ----------------------------------------------------------------

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Group sizes vary by country (US 3-3-4, India 5-5, UK 4-6). Match a run of
# digits with common separators and let `_valid_phone` decide, rather than
# hard-coding one national format and silently dropping the rest.
_PHONE = re.compile(r"(?<![\w/])\+?\(?\d[\d \t().-]{7,16}\d(?![\w/])")
_LINK = re.compile(r"(?:https?://|www\.)[^\s,;)]+|(?:linkedin\.com|github\.com)/[^\s,;)]+", re.IGNORECASE)


def _valid_phone(raw: str) -> bool:
    """Reject year ranges such as `2024 - 2025` that a loose pattern accepts."""
    digits = re.sub(r"\D", "", raw)
    if not 10 <= len(digits) <= 15:
        return False
    if "+" not in raw and "(" not in raw and " " not in raw.strip() and "-" not in raw:
        return False
    return True


def _extract_contact(lines: list[str]) -> Contact:
    scope = "\n".join(lines[:20]) if lines else ""
    body = scope or "\n".join(lines)

    email_match = _EMAIL.search(body)
    phone_match = next(
        (match for match in _PHONE.finditer(body) if _valid_phone(match.group(0))), None
    )
    links = [match.group(0).rstrip(".,;") for match in _LINK.finditer(body)]

    name: str | None = None
    for line in lines[:6]:
        candidate = collapse_spaces(line)
        if not candidate or len(candidate) > 60:
            continue
        if _EMAIL.search(candidate) or _LINK.search(candidate) or re.search(r"\d", candidate):
            continue
        if classify_heading(candidate) is not None:
            continue
        if 1 <= len(candidate.split()) <= 5:
            name = candidate
            break

    return Contact(
        name=name,
        email=email_match.group(0) if email_match else None,
        phone=collapse_spaces(phone_match.group(0)) if phone_match else None,
        links=links,
    )


# --- Block segmentation -----------------------------------------------------


def _segment(lines: list[str], offsets: list[int]) -> tuple[list[str], list[tuple[str, list[tuple[str, int]]]]]:
    """Split the document into a preamble and (kind, lines) blocks."""
    preamble: list[str] = []
    blocks: list[tuple[str, list[tuple[str, int]]]] = []
    current_kind: str | None = None
    current_lines: list[tuple[str, int]] = []

    for line, offset in zip(lines, offsets, strict=True):
        kind = classify_heading(line)
        if kind is not None:
            if current_kind is not None:
                blocks.append((current_kind, current_lines))
            current_kind = kind
            current_lines = []
            continue

        if current_kind is None:
            preamble.append(line)
        else:
            current_lines.append((line, offset))

    if current_kind is not None:
        blocks.append((current_kind, current_lines))

    return preamble, blocks


# --- Experience -------------------------------------------------------------

_COMPANY_HINTS = re.compile(
    r"\b(inc|llc|ltd|limited|corp|corporation|company|technologies|technology|solutions|systems|"
    r"labs|software|consulting|services|group|university|college|institute|school|bank|pvt)\b",
    re.IGNORECASE,
)
_ROLE_SEPARATORS = re.compile(r"\s*(?:\||—|–|\bat\b|@|,)\s*", re.IGNORECASE)


def _split_role_and_org(parts: list[str]) -> tuple[str | None, str | None]:
    """Decide which candidate string is the title and which the employer."""
    cleaned = [part for part in (collapse_spaces(p) for p in parts) if part]
    if not cleaned:
        return None, None

    if len(cleaned) == 1:
        return cleaned[0], None

    first, second = cleaned[0], cleaned[1]
    first_is_company = bool(_COMPANY_HINTS.search(first))
    second_is_company = bool(_COMPANY_HINTS.search(second))

    if second_is_company and not first_is_company:
        return first, second
    if first_is_company and not second_is_company:
        return second, first
    return first, second


def _parse_experience(
    block: list[tuple[str, int]],
    uncertain: list[Uncertainty],
) -> list[ExperienceEntry]:
    entries: list[ExperienceEntry] = []
    header_buffer: list[str] = []
    current: ExperienceEntry | None = None

    for raw_line, offset in block:
        if not raw_line.strip():
            continue

        if is_bullet_line(raw_line):
            text = strip_bullet_marker(raw_line)
            if not text:
                continue
            if current is None:
                # A header without dates is still a role. Keep the title the
                # document actually gives and leave the employer unknown rather
                # than borrowing one from another entry.
                title, organisation = _split_role_and_org(list(header_buffer))
                current = ExperienceEntry(title=title, organisation=organisation)
                entries.append(current)
                header_buffer = []
                index = len(entries) - 1
                uncertain.append(
                    Uncertainty(field=f"experience[{index}].dates", reason="dates_missing")
                )
                if organisation is None:
                    uncertain.append(
                        Uncertainty(
                            field=f"experience[{index}].organisation",
                            reason="organisation_missing",
                        )
                    )
            start = offset + raw_line.find(text)
            current.bullets.append(Bullet(text=text, span=(start, start + len(text))))
            continue

        line = collapse_spaces(raw_line)
        dates = find_date_tokens(line)

        if dates:
            start_date, end_date, precision, ambiguous = parse_date_range(line)
            header_text = strip_date_text(line).strip("|—-–, ")

            # Resume convention: the title line precedes the "company | dates"
            # line, so buffered lines come first and the date line's own text is
            # the employer.
            title, organisation = _split_role_and_org(
                [*header_buffer, header_text] if header_text else list(header_buffer)
            )
            # A single-line header usually carries "Title | Company".
            if header_text and not organisation:
                split_parts = [p for p in _ROLE_SEPARATORS.split(header_text) if p]
                if len(split_parts) > 1:
                    title, organisation = _split_role_and_org(split_parts)

            current = ExperienceEntry(
                title=title,
                organisation=organisation,
                start=start_date,
                end=end_date,
                date_precision=precision,  # type: ignore[arg-type]
            )
            entries.append(current)
            header_buffer = []

            if ambiguous:
                uncertain.append(
                    Uncertainty(
                        field=f"experience[{len(entries) - 1}].dates",
                        reason="date_ambiguous",
                    )
                )
            if title is None:
                uncertain.append(
                    Uncertainty(
                        field=f"experience[{len(entries) - 1}].title", reason="title_missing"
                    )
                )
            if organisation is None:
                uncertain.append(
                    Uncertainty(
                        field=f"experience[{len(entries) - 1}].organisation",
                        reason="organisation_missing",
                    )
                )
            continue

        # No date on this line: buffer it as a possible header or organisation.
        if current is None or not current.bullets:
            header_buffer.append(line)
        else:
            header_buffer = [line]

    return entries


# --- Education --------------------------------------------------------------

_DEGREE = re.compile(
    r"\b(b\.?\s?tech|b\.?\s?e\.?|bachelor(?:'s)?|b\.?sc|b\.?s\.?|m\.?\s?tech|m\.?\s?e\.?|"
    r"master(?:'s)?|m\.?sc|m\.?s\.?|mba|ph\.?\s?d|doctorate|diploma|associate)\b",
    re.IGNORECASE,
)
_INSTITUTION = re.compile(
    r"\b(university|college|institute|school|academy|polytechnic)\b", re.IGNORECASE
)


def _institution_name(line: str, match: re.Match[str]) -> str:
    """Return the whole institution name, not the text up to the keyword.

    "National Institute of Technology" must not be truncated to "National
    Institute" merely because `institute` is the matched keyword: the name is a
    delimiter-separated field, so split on delimiters instead.
    """
    start = 0
    for separator in ("|", ",", ";", "—", "–"):
        index = line.rfind(separator, 0, match.start())
        if index != -1:
            start = max(start, index + len(separator))

    end = len(line)
    for separator in ("|", ",", ";", "—", "–", "("):
        index = line.find(separator, match.end())
        if index != -1:
            end = min(end, index)

    return collapse_spaces(line[start:end]).strip(" .,")


def _parse_education(
    block: list[tuple[str, int]],
    uncertain: list[Uncertainty],
) -> list[EducationEntry]:
    entries: list[EducationEntry] = []
    current: EducationEntry | None = None

    for raw_line, _offset in block:
        if not raw_line.strip():
            continue

        if is_bullet_line(raw_line):
            if current is not None:
                current.details.append(strip_bullet_marker(raw_line))
            continue

        line = collapse_spaces(raw_line)
        starts_entry = bool(_INSTITUTION.search(line) or _DEGREE.search(line))

        # A line naming only the institution continues the entry above it rather
        # than starting a second degree.
        if (
            starts_entry
            and current is not None
            and current.institution is None
            and current.degree is not None
            and _INSTITUTION.search(line)
            and not _DEGREE.search(line)
        ):
            match = _INSTITUTION.search(line)
            assert match is not None
            current.institution = _institution_name(line, match)
            degree_dates = parse_date_range(line)
            if degree_dates[0] or degree_dates[1]:
                current.start, current.end = degree_dates[0], degree_dates[1]
            continue

        if starts_entry or current is None:
            start_date, end_date, _precision, ambiguous = parse_date_range(line)

            institution_match = _INSTITUTION.search(line)
            degree_match = _DEGREE.search(line)

            institution = None
            if institution_match:
                institution = _institution_name(line, institution_match)

            field_name = None
            field_match = re.search(r"\b(?:in|of)\s+([A-Za-z&,\- ]{3,60})", line)
            if field_match and degree_match:
                field_name = collapse_spaces(field_match.group(1)).strip(" ,.")

            current = EducationEntry(
                institution=institution,
                degree=collapse_spaces(degree_match.group(0)) if degree_match else None,
                field=field_name,
                start=start_date,
                end=end_date,
            )
            entries.append(current)

            if ambiguous:
                uncertain.append(
                    Uncertainty(
                        field=f"education[{len(entries) - 1}].dates", reason="date_ambiguous"
                    )
                )
            continue

        # Continuation line for the current entry.
        current.details.append(line)

    # Deferred so that an institution on a following line can attach first.
    for index, entry in enumerate(entries):
        if entry.institution is None:
            uncertain.append(
                Uncertainty(field=f"education[{index}].institution", reason="institution_missing")
            )
        if entry.degree is None:
            uncertain.append(
                Uncertainty(field=f"education[{index}].degree", reason="degree_missing")
            )

    return entries


# --- Projects ---------------------------------------------------------------


def _parse_projects(
    block: list[tuple[str, int]],
    uncertain: list[Uncertainty],
) -> list[ProjectEntry]:
    entries: list[ProjectEntry] = []
    current: ProjectEntry | None = None
    description_parts: list[str] = []

    for raw_line, offset in block:
        if not raw_line.strip():
            continue

        if is_bullet_line(raw_line):
            text = strip_bullet_marker(raw_line)
            if current is None:
                current = ProjectEntry()
                entries.append(current)
                uncertain.append(
                    Uncertainty(field=f"projects[{len(entries) - 1}]", reason="project_name_missing")
                )
            start = offset + raw_line.find(text)
            current.bullets.append(Bullet(text=text, span=(start, start + len(text))))
            description_parts.append(text)
            continue

        line = collapse_spaces(raw_line)
        if current is None or current.bullets or current.description:
            current = ProjectEntry(name=line)
            entries.append(current)
            description_parts = []
        else:
            description_parts.append(line)

        current.description = collapse_spaces(" ".join(description_parts)) or None

    for entry in entries:
        source = " ".join(filter(None, [entry.name, entry.description]))
        entry.technologies = find_skills(source)

    return entries


# --- Skills -----------------------------------------------------------------

_SENTENCE_LIKE = re.compile(r"[.!?]\s+[A-Z]|\b(and|with|using|including)\b", re.IGNORECASE)


def _plausible_raw_skill(token: str) -> bool:
    """Keep unknown-but-plausible skill tokens, reject sentence fragments."""
    if not token or len(token) > 40:
        return False
    if len(token.split()) > 5:
        return False
    if not re.search(r"[A-Za-z]", token):
        return False
    if token.endswith("."):
        return False
    if _SENTENCE_LIKE.search(token):
        return False
    return True


def _parse_skills(block: list[tuple[str, int]]) -> list[str]:
    explicit: list[str] = []
    seen: set[str] = set()
    text = "\n".join(line for line, _ in block)

    for token in split_skill_list(text):
        canonical = canonicalise(token)
        if canonical is not None:
            if canonical.lower() not in seen:
                seen.add(canonical.lower())
                explicit.append(canonical)
            continue

        # "Python and Django" is one token but two skills; recover them from the
        # taxonomy before deciding the token is unusable.
        recovered = find_skills(token, include_ambiguous=True)
        if recovered:
            for name in recovered:
                if name.lower() not in seen:
                    seen.add(name.lower())
                    explicit.append(name)
            continue

        if not _plausible_raw_skill(token):
            continue
        if token.lower() in seen:
            continue
        seen.add(token.lower())
        explicit.append(token)

    return explicit


# --- Certifications / achievements -----------------------------------------


def _parse_certifications(block: list[tuple[str, int]]) -> list[CertificationEntry]:
    entries: list[CertificationEntry] = []
    for raw_line, _offset in block:
        line = collapse_spaces(strip_bullet_marker(raw_line))
        if not line:
            continue

        date_value = None
        dates = find_date_tokens(line)
        if dates:
            date_value = dates[0].value or dates[0].raw
            line = strip_date_text(line).strip("|—-–,() ")

        issuer = None
        for separator in (" - ", " – ", " — ", " by ", ", "):
            if separator in line:
                head, _, tail = line.partition(separator)
                if head.strip() and tail.strip():
                    line, issuer = head.strip(), tail.strip()
                    break

        if line:
            entries.append(CertificationEntry(name=line, issuer=issuer, date=date_value))

    return entries


def _parse_string_list(block: list[tuple[str, int]]) -> list[str]:
    items: list[str] = []
    for raw_line, _offset in block:
        text = strip_bullet_marker(raw_line) if is_bullet_line(raw_line) else collapse_spaces(raw_line)
        if text and not classify_heading(text):
            items.append(text)
    return items


# --- Risk signals -----------------------------------------------------------

_COLUMN_GAP = re.compile(r"\s{3,}")


def _reading_order_risk(text: str, extraction: ExtractionResult) -> str:
    """Estimate layout risk from what extraction actually reported."""
    if extraction.method == "failed":
        return "high"
    if any(warning.startswith("image_only_pages") for warning in extraction.warnings):
        return "high"

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return "high"

    column_like = sum(1 for line in lines if len(_COLUMN_GAP.findall(line)) >= 2)
    ratio = column_like / len(lines)

    if ratio > 0.3:
        return "medium"
    if ratio > 0.1:
        return "low"
    if extraction.method == "partial":
        return "medium"
    return "none"


# --- Entry point ------------------------------------------------------------


def parse_document(extraction: ExtractionResult) -> ResumeStructure:
    """Turn extracted text into `ResumeStructure` (docs/API.md §2.4)."""
    text = normalize_whitespace(extraction.text)
    lines = text.splitlines()

    offsets: list[int] = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line) + 1

    uncertain: list[Uncertainty] = []

    contact = _extract_contact(lines)
    if not contact.email:
        uncertain.append(Uncertainty(field="contact.email", reason="email_not_found"))
    _preamble, blocks = _segment(lines, offsets)

    by_kind: dict[str, list[tuple[str, int]]] = {}
    for kind, block_lines in blocks:
        by_kind.setdefault(kind, []).extend(block_lines)

    summary_text = collapse_spaces(" ".join(line for line, _ in by_kind.get("summary", [])))
    summary = SummaryBlock(text=summary_text or None, present=bool(summary_text))

    experience = _parse_experience(by_kind.get("experience", []), uncertain)
    education = _parse_education(by_kind.get("education", []), uncertain)
    projects = _parse_projects(by_kind.get("projects", []), uncertain)
    explicit_skills = _parse_skills(by_kind.get("skills", []))
    certifications = _parse_certifications(by_kind.get("certifications", []))
    achievements = _parse_string_list(by_kind.get("achievements", []))
    leadership = _parse_string_list(by_kind.get("leadership", []))

    sections = SectionPresence(
        contact=bool(contact.email or contact.phone or contact.links or contact.name),
        summary="summary" in by_kind,
        experience="experience" in by_kind,
        education="education" in by_kind,
        skills="skills" in by_kind,
        projects="projects" in by_kind,
        certifications="certifications" in by_kind,
        achievements="achievements" in by_kind,
        leadership="leadership" in by_kind,
    )

    structure = ResumeStructure(
        contact=contact,
        summary=summary,
        experience=experience,
        education=education,
        projects=projects,
        certifications=certifications,
        achievements=achievements,
        leadership=leadership,
        skills=SkillSet(explicit=explicit_skills),
        sections=sections,
        uncertain=uncertain,
        word_count=word_count(text),
        page_count=max(1, extraction.page_count),
        reading_order_risk=_reading_order_risk(text, extraction),  # type: ignore[arg-type]
    )
    _ = structure.uncertain  # validated copy; further appends must happen above

    # Skills that appear in prose but were never claimed are recorded separately:
    # "used in a bullet" is weaker evidence than "listed as a skill".
    explicit_lookup = {name.lower() for name in explicit_skills}
    substantiated = structure.substantiated_text()
    inferred: list[InferredSkill] = []
    for skill in find_skills(substantiated):
        if skill.lower() in explicit_lookup:
            continue
        inferred.append(
            InferredSkill(name=skill, basis="mentioned in experience or project text")
        )
    structure.skills.inferred = inferred

    all_dates = [
        token for token in find_date_tokens(text) if not token.ambiguous
    ]
    structure.has_dates = bool(all_dates)
    structure.date_formats = sorted({token.precision for token in all_dates if token.precision != "present"})
    structure.bullet_count = len(structure.all_bullets())

    # No experience section is not an error: a first-time candidate legitimately
    # has no work history. `sections.experience` stays False so scoring treats
    # the category as not applicable rather than scoring it zero.
    return structure
