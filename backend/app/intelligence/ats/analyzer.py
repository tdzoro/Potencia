"""ATS compatibility analyzer (AT-01 … AT-05).

This is an *estimate* of how reliably resume software can read a document, not
a prediction of any vendor's screen. Two consequences are enforced in code:

- The report always carries `disclaimer`, as data rather than frontend copy, so
  a client that forgets to render it still receives the truth.
- Document-parse compatibility is kept separate from job-keyword relevance. A
  keyword-perfect resume in a two-column PDF still fails here.

AT-03 reads `layout_hazards` when the parser provides it and reports
`not applicable` when it does not, rather than assuming a clean layout it never
inspected.
"""

from __future__ import annotations

import re

from app.intelligence.scoring.aggregate import (
    clamp,
    make_finding,
    make_result,
    not_applicable,
)
from app.schemas.resume import ResumeStructure
from app.schemas.scores import ATSCheck, ATSReport, CriterionResult, Evidence

READING_ORDER_SCORES = {"none": 1.0, "low": 0.5, "medium": 0.5, "high": 0.2}

# Below this extraction confidence, no amount of clean formatting rescues the
# document: the text a machine sees is not the text the author wrote.
EXTRACTION_FLOOR = 0.5
LOW_EXTRACTION_CAP = 55.0


def _status(subscore: float) -> str:
    if subscore >= 0.95:
        return "pass"
    if subscore >= 0.5:
        return "warn"
    return "fail"


def _severity_for(status: str) -> str:
    return {"pass": "info", "warn": "medium", "fail": "high"}[status]


def _at01(extraction_confidence: float) -> CriterionResult:
    subscore = clamp(extraction_confidence)
    evidence = [
        Evidence(section="document", text=f"extraction confidence {extraction_confidence:.2f}")
    ]
    if subscore >= 0.999:
        return make_result("AT-01", 1.0, detail="text extracts cleanly", evidence=evidence)

    return make_result(
        "AT-01",
        subscore,
        detail=f"extraction confidence {extraction_confidence:.2f}",
        evidence=evidence,
        findings=[
            make_finding(
                "AT-01",
                title="Text does not extract cleanly",
                explanation=(
                    "If a parser cannot recover the text, nothing downstream — keywords, "
                    "dates, contact details — survives the trip."
                ),
                remediation=(
                    "Export the resume as a text-based PDF or DOCX rather than a scan or an "
                    "image. If the file is already digital, re-export from the editor instead "
                    "of printing to an image format."
                ),
                evidence=evidence,
            )
        ],
    )


def _at02(structure: ResumeStructure) -> CriterionResult:
    risk = structure.reading_order_risk
    subscore = READING_ORDER_SCORES[risk]
    evidence = [Evidence(section="document", text=f"reading order risk: {risk}")]

    if subscore >= 0.999:
        return make_result("AT-02", 1.0, detail="single-column reading order", evidence=evidence)

    return make_result(
        "AT-02",
        subscore,
        detail=f"reading order risk {risk}",
        evidence=evidence,
        findings=[
            make_finding(
                "AT-02",
                title="Layout may scramble the reading order",
                explanation=(
                    "Columns and floating blocks are reassembled in unpredictable order, which "
                    "can separate a job title from its dates or its bullets."
                ),
                remediation=(
                    "Use a single-column layout. If columns must stay, keep each role's title, "
                    "employer and dates on one line so they survive reflow together."
                ),
                evidence=evidence,
            )
        ],
    )


def _at03(structure: ResumeStructure) -> CriterionResult:
    hazards = getattr(structure, "layout_hazards", None)
    if hazards is None:
        return not_applicable(
            "AT-03", "layout hazards are not reported by the parser contract"
        )

    count = len(hazards)
    subscore = clamp(1.0 - 0.2 * count)
    evidence = [
        Evidence(section="document", text=str(hazard)) for hazard in list(hazards)[:3]
    ] or [Evidence(section="document", text="no structural hazards")]

    if not count:
        return make_result("AT-03", 1.0, detail="no structural hazards", evidence=evidence)

    return make_result(
        "AT-03",
        subscore,
        detail=f"{count} structural hazard(s)",
        evidence=evidence,
        findings=[
            make_finding(
                "AT-03",
                title="Structural elements confuse extraction",
                explanation=(
                    "Tables, text boxes, images containing text and contact details in headers "
                    "or footers are common places for extraction to silently lose content."
                ),
                remediation=(
                    "Move content out of tables and text boxes into normal paragraphs, and keep "
                    "contact details in the body of the first page rather than a header."
                ),
                evidence=evidence,
            )
        ],
    )


def _at04(structure: ResumeStructure) -> CriterionResult:
    formats = [fmt for fmt in structure.date_formats if fmt]
    if not formats:
        return not_applicable("AT-04", "no dates were parsed, so format cannot be judged")

    # "03/04" could be March or April; "03/2024" carries a year and is safe.
    ambiguous = [
        fmt
        for fmt in formats
        if re.search(r"\d{1,2}/\d{1,2}", fmt) and not re.search(r"(?:19|20)\d{2}", fmt)
    ]
    unique = sorted(set(formats))
    evidence = [Evidence(section="document", text=", ".join(unique[:5]))]

    if ambiguous:
        return make_result(
            "AT-04",
            0.0,
            detail=f"ambiguous date formats: {', '.join(ambiguous[:3])}",
            evidence=evidence,
            findings=[
                make_finding(
                    "AT-04",
                    title="Dates are ambiguous",
                    explanation=(
                        "A numeric date such as 03/04 can be read as March or April depending "
                        "on the parser's locale, which can reorder an entire career history."
                    ),
                    remediation=(
                        "Write dates with a month name or an ISO order: 'Mar 2024' or "
                        "'2024-03'. Apply the same format to every date on the page."
                    ),
                    evidence=evidence,
                )
            ],
        )

    subscore = 1.0 if len(unique) == 1 else 0.5
    if subscore >= 0.999:
        return make_result("AT-04", 1.0, detail="dates are consistent", evidence=evidence)

    return make_result(
        "AT-04",
        subscore,
        detail=f"{len(unique)} different date formats",
        evidence=evidence,
        findings=[
            make_finding(
                "AT-04",
                title="Date formats are mixed",
                explanation=(
                    "Mixed formats are still parseable here, but they increase the chance a "
                    "stricter parser misreads one of them."
                ),
                remediation=(
                    "Pick one format — 'Mar 2024' is unambiguous — and use it for every start "
                    "and end date."
                ),
                evidence=evidence,
            )
        ],
    )


def _at05(structure: ResumeStructure) -> CriterionResult:
    contact = structure.contact
    present = sum(1 for value in (contact.email, contact.phone) if value)
    subscore = {2: 1.0, 1: 0.5, 0: 0.0}[present]
    evidence = [
        Evidence(
            section="contact",
            text=" ".join(filter(None, [contact.email, contact.phone])) or "<no contact details parsed>",
        )
    ]

    if subscore >= 0.999:
        return make_result("AT-05", 1.0, detail="email and phone parse as text", evidence=evidence)

    return make_result(
        "AT-05",
        subscore,
        detail="email and phone are not both recoverable",
        evidence=evidence,
        findings=[
            make_finding(
                "AT-05",
                title="Contact details are not fully recoverable",
                explanation=(
                    "An email or phone number that exists only as an image, or inside a header "
                    "element, may never reach the recruiting system."
                ),
                remediation=(
                    "Type the email address and phone number as plain text in the body of the "
                    "document, not inside a graphic or a header block."
                ),
                evidence=evidence,
            )
        ],
    )


CHECKS = {
    "AT-01": ("Extraction fidelity", "Text can be recovered from the document"),
    "AT-02": ("Reading order", "Single-column reading order is preserved"),
    "AT-03": ("Structural hazards", "No tables, text boxes or embedded text"),
    "AT-04": ("Date parseability", "Dates are consistent and unambiguous"),
    "AT-05": ("Contact parseability", "Email and phone are recoverable as text"),
}


def _to_check(result: CriterionResult) -> ATSCheck:
    label, description = CHECKS[result.criterion]
    status = _status(result.subscore)
    evidence = result.evidence or [Evidence(section="document", text=description)]
    if result.findings:
        explanation = result.findings[0].explanation
        remediation = result.findings[0].remediation
    else:
        explanation = description
        remediation = "No change needed."

    return ATSCheck(
        id=result.criterion,
        label=label,
        status=status,  # type: ignore[arg-type]
        severity=_severity_for(status),  # type: ignore[arg-type]
        evidence=evidence,
        explanation=explanation,
        remediation=remediation,
    )


def analyze_ats(
    structure: ResumeStructure, extraction_confidence: float
) -> tuple[ATSReport, list[CriterionResult]]:
    """Run the five ATS checks and return the report plus its scored criteria."""
    criteria = [
        _at01(extraction_confidence),
        _at02(structure),
        _at03(structure),
        _at04(structure),
        _at05(structure),
    ]

    applicable = [c for c in criteria if c.applicable]
    total_weight = sum(c.weight for c in applicable) or 1
    estimate = 100.0 * sum(c.weight * c.subscore for c in applicable) / total_weight

    # A document whose text barely extracts cannot be "compatible" no matter how
    # tidy its formatting looks to us.
    if extraction_confidence < EXTRACTION_FLOOR:
        estimate = min(estimate, LOW_EXTRACTION_CAP)

    checks = [_to_check(c) for c in applicable]
    summary = {
        "pass": sum(1 for check in checks if check.status == "pass"),
        "warn": sum(1 for check in checks if check.status == "warn"),
        "fail": sum(1 for check in checks if check.status == "fail"),
    }

    report = ATSReport(
        estimate=round(estimate, 1),
        checks=checks,
        summary=summary,
    )
    return report, criteria
