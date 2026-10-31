"""Structure criteria (ST-01 … ST-05).

Two of these criteria need information the current parser contract does not
expose: the order of sections and the literal heading labels. Rather than
inventing a pass, they read optional attributes (`section_order`, `headings`)
and report `not applicable` when absent — the denominator shrinks, and the
score stays honest. See the module's closing note.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.intelligence.scoring.aggregate import (
    experience_is_applicable,
    make_finding,
    make_result,
    not_applicable,
)
from app.intelligence.scoring.experience import parse_year_month
from app.schemas.resume import ResumeStructure
from app.schemas.scores import CriterionResult, Evidence

CANONICAL_HEADINGS = frozenset(
    {
        "summary", "profile", "objective", "experience", "work experience",
        "employment", "education", "skills", "technical skills", "projects",
        "certifications", "achievements", "awards", "leadership", "contact",
    }
)


def _st01(structure: ResumeStructure) -> CriterionResult:
    expected = ["contact", "summary", "education", "skills"]
    presence = {
        "contact": bool(structure.contact.email or structure.contact.phone or structure.contact.name),
        "summary": structure.summary.present and bool(structure.summary.text),
        "education": bool(structure.education),
        "skills": bool(structure.skills.explicit or structure.skills.inferred),
    }
    if experience_is_applicable(structure):
        expected.append("experience")
        presence["experience"] = bool(structure.experience)

    present = [name for name in expected if presence[name]]
    missing = [name for name in expected if not presence[name]]
    subscore = len(present) / len(expected)

    evidence = [Evidence(section="document", text="missing: " + ", ".join(missing))] if missing else [
        Evidence(section="document", text="present: " + ", ".join(present))
    ]

    if not missing:
        return make_result("ST-01", 1.0, detail="all expected sections present", evidence=evidence)

    return make_result(
        "ST-01",
        subscore,
        detail="missing sections: " + ", ".join(missing),
        evidence=evidence,
        findings=[
            make_finding(
                "ST-01",
                title="Expected sections are missing",
                explanation=(
                    "Missing " + ", ".join(missing) + " makes the resume harder to parse and "
                    "leaves a reader without information they expect to find."
                ),
                remediation=(
                    "Add each missing section with a conventional heading. If a section truly "
                    "does not apply to you, say so in one line rather than omitting it — for "
                    "example a candidate with no work history can lead with projects."
                ),
                evidence=evidence,
            )
        ],
    )


def _st02(structure: ResumeStructure) -> CriterionResult:
    order = getattr(structure, "section_order", None)
    if not order:
        return not_applicable(
            "ST-02",
            "section order is not exposed by the parser contract, so ordering cannot be judged",
        )

    kinds = [str(kind).lower() for kind in order]
    inversions = 0
    if kinds and kinds[0] != "contact":
        inversions += 1
    if "summary" in kinds and "experience" in kinds and kinds.index("summary") > kinds.index("experience"):
        inversions += 1
    if "education" in kinds and "experience" in kinds:
        # After experience is conventional once there is work history.
        if experience_is_applicable(structure) and kinds.index("education") < kinds.index("experience"):
            inversions += 1

    subscore = 1.0 if inversions == 0 else (0.5 if inversions == 1 else 0.0)
    evidence = [Evidence(section="document", text=" → ".join(kinds))]

    if inversions == 0:
        return make_result("ST-02", 1.0, detail="section order is conventional", evidence=evidence)

    return make_result(
        "ST-02",
        subscore,
        detail=f"{inversions} ordering inversion(s)",
        evidence=evidence,
        findings=[
            make_finding(
                "ST-02",
                title="Sections are out of the expected order",
                explanation="Readers scan in a predictable order; an inversion costs attention.",
                remediation=(
                    "Put contact details first, then the summary, then experience, then "
                    "education and skills. Move education above experience only if you are "
                    "still studying or recently graduated."
                ),
                evidence=evidence,
            )
        ],
    )


def _st03(structure: ResumeStructure) -> CriterionResult:
    headings = getattr(structure, "headings", None)
    if not headings:
        return not_applicable(
            "ST-03",
            "heading labels are not exposed by the parser contract, so clarity cannot be judged",
        )

    canonical = [h for h in headings if str(h).strip().lower() in CANONICAL_HEADINGS]
    ratio = len(canonical) / len(headings)
    evidence = [
        Evidence(section="document", text=", ".join(str(h) for h in headings[:8]))
    ]

    if ratio >= 0.999:
        return make_result("ST-03", 1.0, detail="headings are conventional", evidence=evidence)

    return make_result(
        "ST-03",
        ratio,
        detail=f"{len(headings) - len(canonical)} non-standard heading(s)",
        evidence=evidence,
        findings=[
            make_finding(
                "ST-03",
                title="Some headings are non-standard",
                explanation=(
                    "Creative headings can be missed by both a reader in a hurry and by "
                    "software looking for a known section name."
                ),
                remediation=(
                    "Rename headings to the conventional form: Experience, Education, Skills, "
                    "Projects. Personality belongs in the content, not the labels."
                ),
                evidence=evidence,
            )
        ],
    )


def _st04(structure: ResumeStructure) -> CriterionResult:
    years = None
    current_year = datetime.now(timezone.utc).year
    starts = [parse_year_month(role.start) for role in structure.experience]
    parsed = [start for start in starts if start]
    if parsed:
        years = current_year - min(start[0] for start in parsed)

    if years is None:
        return not_applicable("ST-04", "no parseable dates to relate length to experience")

    allowed = 1 if years < 8 else 2
    pages = structure.page_count or 1
    evidence = [Evidence(section="document", text=f"{pages} page(s) for {years} year(s) of experience")]

    if pages <= allowed:
        return make_result("ST-04", 1.0, detail=f"{pages} pages within the {allowed}-page band", evidence=evidence)

    subscore = 0.5 if pages == allowed + 1 else 0.0
    return make_result(
        "ST-04",
        subscore,
        detail=f"{pages} pages exceeds the {allowed}-page band",
        evidence=evidence,
        findings=[
            make_finding(
                "ST-04",
                title="The document is longer than its experience warrants",
                explanation=(
                    f"At {years} years of experience the conventional length is {allowed} page(s). "
                    "Length itself is not merit; padding dilutes what matters."
                ),
                remediation=(
                    "Cut the least relevant role detail first, then repeated tools and generic "
                    "statements. Keep the bullets that carry a measurable outcome."
                ),
                evidence=evidence,
            )
        ],
    )


def _st05(structure: ResumeStructure) -> CriterionResult:
    contact = structure.contact
    evidence = [
        Evidence(
            section="contact",
            text=" ".join(filter(None, [contact.name, contact.email, contact.phone, *(contact.links[:2])]))
            or "<no contact block found>",
        )
    ]

    if not contact.email:
        return make_result(
            "ST-05",
            0.0,
            detail="no email address",
            evidence=evidence,
            findings=[
                make_finding(
                    "ST-05",
                    title="No email address in the contact block",
                    explanation="Without a reachable address the resume cannot be acted on.",
                    remediation=(
                        "Add a professional email address in the contact block at the top of "
                        "the first page, as plain text."
                    ),
                    evidence=evidence,
                )
            ],
        )

    if not (contact.phone or contact.links):
        return make_result(
            "ST-05",
            0.5,
            detail="email present, no phone or profile link",
            evidence=evidence,
            findings=[
                make_finding(
                    "ST-05",
                    title="Only an email address is provided",
                    explanation=(
                        "A second contact route lets a recruiter reach you if the first fails."
                    ),
                    remediation=(
                        "Add a phone number or a professional profile link beside the email."
                    ),
                    evidence=evidence,
                )
            ],
        )

    return make_result("ST-05", 1.0, detail="contact details are complete", evidence=evidence)


def evaluate(structure: ResumeStructure) -> list[CriterionResult]:
    return [
        _st01(structure),
        _st02(structure),
        _st03(structure),
        _st04(structure),
        _st05(structure),
    ]
