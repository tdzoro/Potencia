"""Property tests for the two boundaries most likely to invent evidence.

Dates must either round-trip to a real calendar date or stay unknown; a short
skill name must never be found inside a longer word. Hypothesis generates the
inputs, so the assertions cover shapes no hand-written fixture happened to use.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date

from hypothesis import given, settings
from hypothesis import strategies as st

from app.intelligence.normalization import find_date_tokens, normalize_date
from app.intelligence.scoring.experience import parse_year_month
from app.intelligence.taxonomy import contains_skill, split_supported_skills

MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

SHORT_SKILLS = ("R", "C", "Go", "Swift", "Spring")
WORD_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


@settings(max_examples=150, deadline=None)
@given(st.dates(min_value=date(1900, 1, 1), max_value=date(2099, 12, 31)))
def test_every_real_day_round_trips(value: date) -> None:
    raw = f"{value.day} {MONTH_NAMES[value.month - 1]} {value.year}"
    parsed = normalize_date(raw)

    assert parsed.value == value.isoformat()
    assert parsed.precision == "day"
    assert parse_year_month(parsed.value) == (value.year, value.month)


@settings(max_examples=150, deadline=None)
@given(st.integers(min_value=1900, max_value=2099), st.integers(min_value=1, max_value=12))
def test_every_month_name_round_trips(year: int, month: int) -> None:
    parsed = normalize_date(f"{MONTH_NAMES[month - 1]} {year}")

    assert parsed.value == f"{year}-{month:02d}"
    assert parsed.precision == "month"
    assert parse_year_month(parsed.value) == (year, month)


@settings(max_examples=100, deadline=None)
@given(
    st.integers(min_value=1900, max_value=2099),
    st.sampled_from((2, 4, 6, 9, 11)),
)
def test_impossible_calendar_days_stay_unknown(year: int, month: int) -> None:
    # None of these months has a 31st, so every generated input is impossible.
    parsed = normalize_date(f"31/{month}/{year}")

    assert parsed.value is None
    assert parsed.precision == "unknown"


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=60))
def test_date_normalisation_is_total_and_never_invents_a_date(text: str) -> None:
    parsed = normalize_date(text)

    assert parsed.precision in {"day", "month", "year", "present", "unknown"}
    if parsed.value is not None:
        assert re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", parsed.value)
        if len(parsed.value) == 10:
            date.fromisoformat(parsed.value)  # raises if a calendar date was invented
        assert parse_year_month(parsed.value) is not None

    tokens = find_date_tokens(text)
    assert all(token.raw in text for token in tokens)


@settings(max_examples=150, deadline=None)
@given(
    st.text(alphabet=WORD_CHARS, min_size=1, max_size=12),
    st.text(alphabet=WORD_CHARS, min_size=1, max_size=12),
    st.sampled_from(SHORT_SKILLS),
)
def test_short_skill_is_not_found_inside_a_word(prefix: str, suffix: str, skill: str) -> None:
    assert not contains_skill(f"{prefix}{skill}{suffix}", skill)
    assert contains_skill(f"{prefix} {skill} {suffix}", skill)


@settings(max_examples=150, deadline=None)
@given(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=4, max_size=12),
    st.booleans(),
)
def test_unknown_skills_also_require_a_whole_mention(token: str, uppercase: bool) -> None:
    name = token.upper() if uppercase else token

    assert contains_skill(f"Built {name} services", name)
    assert not contains_skill(f"pre{name}post", name)


@settings(max_examples=150, deadline=None)
@given(
    st.lists(st.sampled_from(["Python", "R", "Kubernetes", "Zorblatt", "JS", "Go"]), max_size=12),
    st.text(max_size=50),
)
def test_supported_skill_partition_loses_nothing(names: list[str], text: str) -> None:
    supported, unsupported = split_supported_skills(text, names)

    assert Counter(supported) + Counter(unsupported) == Counter(names)
