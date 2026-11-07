"""Skills criteria (SK-01 … SK-05).

SK-04 is the honesty criterion: it rewards a short, defensible list over a wall
of keywords. A low SK-04 produces "substantiate or remove" advice, never
"add more keywords" (§4.3).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache

from app.intelligence.scoring.aggregate import clamp, make_finding, make_result, not_applicable
from app.intelligence.scoring.experience import parse_year_month
from app.intelligence.taxonomy import split_supported_skills
from app.schemas.resume import ResumeStructure
from app.schemas.scores import CriterionResult, Evidence

ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "reactjs": "react",
    "react.js": "react",
    "node": "node.js",
    "nodejs": "node.js",
    "postgres": "postgresql",
    "postgre": "postgresql",
    "k8s": "kubernetes",
    "ml": "machine learning",
    "py": "python",
}

CLUSTERS: dict[str, frozenset[str]] = {
    "languages": frozenset(
        {"python", "java", "javascript", "typescript", "c", "c++", "c#", "go", "rust",
         "ruby", "php", "swift", "kotlin", "sql", "bash", "scala", "r", "dart"}
    ),
    "frameworks": frozenset(
        {"react", "angular", "vue", "django", "flask", "fastapi", "spring", "rails",
         "laravel", "next.js", "express", "svelte", "tailwind"}
    ),
    "tools": frozenset(
        {"git", "docker", "kubernetes", "jenkins", "terraform", "ansible", "linux",
         "jira", "figma", "postman", "gradle", "maven"}
    ),
    "data": frozenset(
        {"postgresql", "mysql", "mongodb", "redis", "kafka", "spark", "hadoop",
         "snowflake", "airflow", "elasticsearch", "sqlite", "dynamodb"}
    ),
    "cloud": frozenset({"aws", "azure", "gcp", "firebase", "heroku", "vercel", "netlify"}),
}

_RECENT_YEARS = 5


_WHITESPACE_RE = re.compile(r"\s+")


@lru_cache(maxsize=2048)
def _fold(name: str) -> str:
    """Case- and whitespace-folded skill name. Cached: the same skills are
    normalised repeatedly across SK-02 through SK-05 for one document."""
    return _WHITESPACE_RE.sub(" ", name.strip().lower())


def canonical(name: str) -> str:
    cleaned = _fold(name)
    return ALIASES.get(cleaned, cleaned)


def _cluster_of(skill: str) -> str | None:
    for cluster, members in CLUSTERS.items():
        if skill in members:
            return cluster
    return None


def _evidence(skills: list[str]) -> list[Evidence]:
    return [Evidence(section="skills", text=", ".join(skills[:8]) or "<no skills section>")]


def _sk01(explicit: list[str], inferred: list[str]) -> CriterionResult:
    if not explicit and not inferred:
        evidence = [Evidence(section="skills", text="<no skills section found>")]
        return make_result(
            "SK-01",
            0.0,
            detail="no skills listed anywhere",
            evidence=evidence,
            findings=[
                make_finding(
                    "SK-01",
                    title="No skills section",
                    explanation=(
                        "A reader looking for a specific technology has nothing to scan for, "
                        "and automated keyword matching has nothing to match."
                    ),
                    remediation=(
                        "Add a skills section grouped by kind — languages, frameworks, tools, "
                        "data stores — listing only what you would defend in an interview."
                    ),
                    evidence=evidence,
                )
            ],
        )

    distinct = {canonical(skill) for skill in [*explicit, *inferred] if skill}
    subscore = clamp(len(distinct) / 10)
    evidence = _evidence(sorted(distinct))

    if subscore >= 0.999:
        return make_result("SK-01", 1.0, detail=f"{len(distinct)} distinct skills", evidence=evidence)

    return make_result(
        "SK-01",
        subscore,
        detail=f"only {len(distinct)} distinct skills listed",
        evidence=evidence,
        findings=[
            make_finding(
                "SK-01",
                title="The skill list is thin",
                explanation=(
                    "With few skills named, there is little for a recruiter — or a keyword "
                    "filter — to match against the role."
                ),
                remediation=(
                    "List the languages, frameworks, tools and data stores you have actually "
                    "used. Do not pad the list with skills you have only read about; every "
                    "entry should be defensible in an interview."
                ),
                evidence=evidence,
            )
        ],
    )


def _sk02(explicit: list[str]) -> CriterionResult:
    if not explicit:
        return not_applicable("SK-02", "no explicit skill list to judge organisation")

    clusters = {c for c in (_cluster_of(canonical(skill)) for skill in explicit) if c}
    evidence = _evidence(explicit)

    if len(clusters) >= 2 and len(explicit) >= 6:
        return make_result("SK-02", 1.0, detail=f"skills span {len(clusters)} groups", evidence=evidence)

    subscore = 0.5 if len(explicit) >= 3 else 0.0
    return make_result(
        "SK-02",
        subscore,
        detail="skills are presented as a flat list",
        evidence=evidence,
        findings=[
            make_finding(
                "SK-02",
                title="Skills are not grouped",
                explanation=(
                    "A flat list of every technology makes it harder to find the one thing a "
                    "reader is scanning for."
                ),
                remediation=(
                    "Group the list by kind — Languages, Frameworks, Data, Tools — and order "
                    "each group by relevance to the role you are targeting."
                ),
                evidence=evidence,
            )
        ],
    )


def _sk03(explicit: list[str]) -> CriterionResult:
    if not explicit:
        return not_applicable("SK-03", "no explicit skill list to check for duplicates")

    canonicals = [canonical(skill) for skill in explicit]
    # One pass. Counting each entry against the whole list is quadratic, and this
    # runs on every analysis.
    counts = Counter(canonicals)
    duplicates = sorted(skill for skill, count in counts.items() if count > 1)
    subscore = clamp(1.0 - 0.15 * len(duplicates))
    evidence = [Evidence(section="skills", text=", ".join(duplicates))] if duplicates else _evidence(explicit)

    if not duplicates:
        return make_result("SK-03", 1.0, detail="no duplicates", evidence=evidence)

    return make_result(
        "SK-03",
        subscore,
        detail=f"duplicated or aliased skills: {', '.join(duplicates)}",
        evidence=evidence,
        findings=[
            make_finding(
                "SK-03",
                title="Duplicated skill entries",
                explanation=(
                    "The same skill appears more than once, which reads as padding and wastes "
                    "space that another skill could use."
                ),
                remediation=(
                    "Keep one spelling of each skill and remove the alias. If two entries "
                    "differ meaningfully, name them so a reader can tell them apart."
                ),
                evidence=evidence,
            )
        ],
    )


def _sk04(structure: ResumeStructure, explicit: list[str]) -> CriterionResult:
    if not explicit:
        return not_applicable("SK-04", "no explicit skill list to verify")

    text = structure.skill_evidence_text()
    _, unsupported = split_supported_skills(text, explicit)
    ratio = (len(explicit) - len(unsupported)) / len(explicit)
    subscore = clamp(ratio / 0.7)
    evidence = [Evidence(section="skills", text=", ".join(unsupported[:8]))] if unsupported else _evidence(explicit)

    if subscore >= 0.999:
        return make_result("SK-04", 1.0, detail="every claimed skill is substantiated", evidence=evidence)

    return make_result(
        "SK-04",
        subscore,
        detail=f"{len(unsupported)} of {len(explicit)} skills never appear outside the skills list",
        evidence=evidence,
        findings=[
            make_finding(
                "SK-04",
                title="Some skills are claimed but never demonstrated",
                explanation=(
                    "A skill that appears only in the list, and nowhere in the work history, "
                    "reads as an assertion rather than evidence."
                ),
                remediation=(
                    "Either add a bullet showing where you used each skill, or remove it. "
                    "Removing an unsupported skill strengthens the list — do not add more "
                    "keywords to compensate."
                ),
                evidence=evidence,
            )
        ],
    )


def _sk05(structure: ResumeStructure, explicit: list[str]) -> CriterionResult:
    if not explicit:
        return not_applicable("SK-05", "no explicit skill list to age")

    current_year = datetime.now(timezone.utc).year
    recent_text_parts: list[str] = []
    dated_roles = 0

    for role in structure.experience:
        start = parse_year_month(role.start)
        end_year = None
        if role.end:
            parsed = parse_year_month(role.end)
            end_year = parsed[0] if parsed else None
        else:
            end_year = current_year
        if end_year is None and start is None:
            continue
        dated_roles += 1
        # A missing end means the role is ongoing; an unparseable explicit end
        # is unknown and must not be interpreted as current.
        if end_year is not None and end_year >= current_year - _RECENT_YEARS:
            recent_text_parts.extend(bullet.text for bullet in role.bullets)

    if dated_roles == 0:
        return not_applicable("SK-05", "no parseable dates to establish recency")

    recent_text = " ".join(recent_text_parts)
    recent, _ = split_supported_skills(recent_text, explicit)
    ratio = len(recent) / len(explicit)
    subscore = clamp(ratio / 0.6)

    evidence = _evidence(recent or explicit)
    if subscore >= 0.999:
        return make_result("SK-05", 1.0, detail="skills are in recent use", evidence=evidence)

    return make_result(
        "SK-05",
        subscore,
        detail="few claimed skills appear in recent roles",
        evidence=evidence,
        findings=[
            make_finding(
                "SK-05",
                title="Some skills are not evidenced recently",
                explanation=(
                    "Skills that only appear in older roles suggest they may not be current."
                ),
                remediation=(
                    "Either show where a skill was used recently, or move it lower in the list "
                    "so the reader's attention goes to what you currently work with."
                ),
                evidence=evidence,
            )
        ],
    )


def evaluate(structure: ResumeStructure) -> list[CriterionResult]:
    explicit = [skill for skill in structure.skills.explicit if skill.strip()]
    inferred = [skill.name for skill in structure.skills.inferred if skill.name.strip()]

    return [
        _sk01(explicit, inferred),
        _sk02(explicit),
        _sk03(explicit),
        _sk04(structure, explicit),
        _sk05(structure, explicit),
    ]
