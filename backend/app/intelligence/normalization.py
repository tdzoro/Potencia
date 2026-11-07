"""Text and date normalisation.

Every function here is deterministic and total: given the same input it returns
the same output, and it never raises on malformed input. An ambiguous date stays
ambiguous — "03/04" could be March or April, and guessing would put a wrong
employment period into an analysis that the user is meant to trust.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

_MONTHS: dict[str, int] = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

_PRESENT_WORDS = {"present", "current", "currently", "now", "ongoing", "today"}

# Ordered: most specific first. Each capture group set maps to a precision.
_DATE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # 14 Mar 2024 / 14th March, 2024
    (
        re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_ALT})\.?,?\s+(\d{{4}})\b", re.IGNORECASE),
        "day",
    ),
    # March 14, 2024
    (
        re.compile(rf"\b({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.IGNORECASE),
        "day",
    ),
    # 14/03/2024 or 03-14-2024 (assumed day-first only when unambiguous)
    (re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b"), "day_slash"),
    # Mar 2024 / March, 2024
    (re.compile(rf"\b({_MONTH_ALT})\.?,?\s+(\d{{4}})\b", re.IGNORECASE), "month_name"),
    # 2024-03
    (re.compile(r"\b(\d{4})-(\d{2})\b"), "iso_month"),
    # 03/2024
    (re.compile(r"\b(\d{1,2})/(\d{4})\b"), "month_slash"),
    # 03/04 — month and day with no year: genuinely ambiguous
    (re.compile(r"\b(\d{1,2})/(\d{1,2})\b(?!\s*/?\s*\d{4})"), "ambiguous_slash"),
    # 2024
    (re.compile(r"\b(19|20)\d{2}\b"), "year"),
)

_PRESENT_PATTERN = re.compile(
    r"\b(" + "|".join(sorted(_PRESENT_WORDS, key=len, reverse=True)) + r")\b", re.IGNORECASE
)


@dataclass(frozen=True)
class DateValue:
    """A parsed date or an explicit statement that we could not resolve it."""

    value: str | None
    precision: str  # day | month | year | present | unknown
    ambiguous: bool = False
    raw: str = ""


def _valid_month(value: int) -> bool:
    return 1 <= value <= 12


def _valid_day(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def normalize_date(raw: str) -> DateValue:
    """Parse one date token. Returns precision `unknown` when it cannot be."""
    text = (raw or "").strip()
    if not text:
        return DateValue(None, "unknown", raw=raw)

    if _PRESENT_PATTERN.fullmatch(text) or text.lower() in _PRESENT_WORDS:
        return DateValue(None, "present", raw=raw)

    for pattern, kind in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue

        if kind == "year":
            return DateValue(match.group(0), "year", raw=raw)

        if kind == "day":
            month_name = match.group(2).lower() if match.group(1).isdigit() else match.group(1).lower()
            month = _MONTHS.get(month_name[:3], 0) or _MONTHS.get(month_name, 0)
            day = match.group(1) if match.group(1).isdigit() else match.group(2)
            year = match.group(3)
            if not _valid_month(month) or not _valid_day(int(year), month, int(day)):
                # A date with an explicit impossible day is unknown, not a
                # month-precision date: 31 February must not become February.
                return DateValue(None, "unknown", ambiguous=True, raw=raw)
            return DateValue(f"{year}-{month:02d}-{int(day):02d}", "day", raw=raw)

        if kind == "day_slash":
            first, second, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            if _valid_month(first) and _valid_day(year, first, second):
                return DateValue(f"{year}-{first:02d}-{second:02d}", "day", raw=raw)
            # Day-first convention (14/03/2024) arrives here.
            if _valid_month(second) and _valid_day(year, second, first):
                return DateValue(f"{year}-{second:02d}-{first:02d}", "day", raw=raw)
            return DateValue(None, "unknown", ambiguous=True, raw=raw)

        if kind == "month_name":
            month = _MONTHS.get(match.group(1).lower()[:3], 0)
            if not _valid_month(month):
                continue
            return DateValue(f"{match.group(2)}-{month:02d}", "month", raw=raw)

        if kind == "iso_month":
            month = int(match.group(2))
            if not _valid_month(month):
                return DateValue(None, "unknown", ambiguous=True, raw=raw)
            return DateValue(f"{match.group(1)}-{month:02d}", "month", raw=raw)

        if kind == "month_slash":
            month = int(match.group(1))
            if not _valid_month(month):
                return DateValue(None, "unknown", ambiguous=True, raw=raw)
            return DateValue(f"{match.group(2)}-{month:02d}", "month", raw=raw)

        if kind == "ambiguous_slash":
            return DateValue(None, "unknown", ambiguous=True, raw=raw)

    return DateValue(None, "unknown", raw=raw)


def find_date_tokens(text: str) -> list[DateValue]:
    """All date-like tokens in order of appearance, without overlapping matches."""
    results: list[DateValue] = []
    consumed: list[tuple[int, int]] = []

    for pattern, _kind in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(start < c_end and end > c_start for c_start, c_end in consumed):
                continue
            consumed.append((start, end))
            results.append(normalize_date(match.group(0)))

    results.sort(key=lambda value: text.find(value.raw))
    return results


def strip_date_text(text: str) -> str:
    """Remove date tokens *and* present markers, leaving the descriptive text.

    "Mar 2022 - Present" must reduce to nothing; leaving "Present" behind would
    put it into the employer name.
    """
    result = _PRESENT_PATTERN.sub(" ", text)
    for token in find_date_tokens(text):
        result = result.replace(token.raw, " ")
    return collapse_spaces(result)


def parse_date_range(text: str) -> tuple[str | None, str | None, str, bool]:
    """Extract (start, end, precision, ambiguous) from a line like `Mar 2024 – Present`.

    An open-ended role reports `end=None` with precision `present`, which is what
    docs/API.md §2.4 requires. "Present" is not a date token, so it is detected
    separately rather than being left to look like a missing end date.
    """
    tokens = find_date_tokens(text)
    has_present = bool(_PRESENT_PATTERN.search(text))

    if not tokens:
        return (None, None, "present", False) if has_present else (None, None, "unknown", False)

    ambiguous = any(token.ambiguous for token in tokens)
    first = tokens[0]
    second = tokens[1] if len(tokens) > 1 else None

    if has_present:
        return (first.value if first.precision != "present" else None), None, "present", ambiguous

    start = first.value if first.precision != "present" else None
    if second is None:
        precision = first.precision if first.precision != "present" else "present"
        return start, None, precision, ambiguous

    if second.precision == "present":
        return start, None, "present", ambiguous

    precision = "month" if first.precision == "month" or second.precision == "month" else first.precision
    return start, second.value, precision, ambiguous


# --- Text ------------------------------------------------------------------

_WHITESPACE = re.compile(r"[ \t\u00a0]+")
_BULLET_MARKER = re.compile(r"^\s*(?:[•●▪◦‣·*\-–—]|\(?\d{1,2}[.)]|[a-zA-Z][.)])\s+")


def normalize_whitespace(text: str) -> str:
    """Collapse horizontal whitespace but preserve line structure."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines)


def collapse_spaces(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def is_bullet_line(line: str) -> bool:
    return bool(_BULLET_MARKER.match(line))


def strip_bullet_marker(line: str) -> str:
    return _BULLET_MARKER.sub("", line, count=1).strip()


def clean_heading(line: str) -> str:
    """Headings lose decoration: bullets, colons, surrounding punctuation, extra space."""
    text = strip_bullet_marker(line)
    text = collapse_spaces(text)
    text = text.strip(":;|•–—- ")
    return text


_LIST_SPLIT = re.compile(r"\s*[,;|•·]\s*|\s{3,}")


def split_skill_list(text: str) -> list[str]:
    """Split a skills block into tokens.

    Slashes are not separators: `C/C++` and `CI/CD` are single skills, and
    splitting on them would invent two wrong ones.
    """
    items: list[str] = []
    for line in text.splitlines():
        for chunk in _LIST_SPLIT.split(line):
            token = chunk.strip(" .;:•-–—|")
            if token:
                items.append(token)
    return items


def word_count(text: str) -> int:
    return len([word for word in re.split(r"\s+", text) if word.strip()])


_QUANTITY = re.compile(r"\d")


def has_number(text: str) -> bool:
    return bool(_QUANTITY.search(text))
