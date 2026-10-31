"""Document rendering for exports (docs/API.md §3.8).

Three artefacts are produced here, all from the same structured data the API
already returns:

* an analysis report (PDF) — the evidence, the numbers and the next actions;
* an improved resume (PDF and DOCX) — the user-approved structure, laid out so
  it stays readable and machine-parseable.

Nothing is re-derived during rendering. If the report says 86.7, that number was
computed by the scoring engine and stored; the renderer only formats it.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.schemas.resume import ResumeStructure

INK = colors.HexColor("#12121A")
MUTED = colors.HexColor("#5A5A6E")
ACCENT = colors.HexColor("#6D3BF5")
RULE = colors.HexColor("#E3E3EC")
BAND_COLORS = {
    "critical": colors.HexColor("#C0392B"),
    "developing": colors.HexColor("#C67C0E"),
    "competent": colors.HexColor("#2C7A7B"),
    "strong": colors.HexColor("#1F7A5C"),
    "exceptional": colors.HexColor("#14532D"),
}
SEVERITY_COLORS = {
    "critical": colors.HexColor("#C0392B"),
    "high": colors.HexColor("#D35400"),
    "medium": colors.HexColor("#C67C0E"),
    "low": colors.HexColor("#4A5568"),
    "info": colors.HexColor("#4A5568"),
}


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "PotenciaTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "PotenciaSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=MUTED,
        ),
        "h2": ParagraphStyle(
            "PotenciaH2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=INK,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "PotenciaBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=INK,
        ),
        "small": ParagraphStyle(
            "PotenciaSmall",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=MUTED,
        ),
        "cell": ParagraphStyle(
            "PotenciaCell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=INK,
        ),
        "cell_head": ParagraphStyle(
            "PotenciaCellHead",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=colors.white,
        ),
        "score": ParagraphStyle(
            "PotenciaScore",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=40,
            leading=44,
            textColor=INK,
        ),
        "name": ParagraphStyle(
            "PotenciaName",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=INK,
            spaceAfter=2,
        ),
        "role": ParagraphStyle(
            "PotenciaRole",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=INK,
        ),
    }


def _table_header(labels: list[str], widths: list[float], style: dict) -> Table:
    row = [Paragraph(escape(label), style["cell_head"]) for label in labels]
    table = Table([row], colWidths=widths)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), ACCENT),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _bullets(items: list[str], style: dict, bullet_color: str = "#6D3BF5") -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(escape(item), style["body"]), leftIndent=12) for item in items],
        bulletType="bullet",
        start="•",
        bulletFontSize=7,
        bulletColor=colors.HexColor(bullet_color),
        leftIndent=10,
        spaceBefore=2,
    )


def _money_fmt(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}"


# --------------------------------------------------------------------------- #
# Analysis report                                                              #
# --------------------------------------------------------------------------- #


def render_analysis_report(report: dict[str, Any], *, filename: str, generated_at: datetime) -> bytes:
    """Render the stored analysis as a paginated PDF.

    `report` is exactly the `/analyses/{id}/report` payload, so the PDF and the
    screen can never disagree.
    """
    style = _styles()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="POTENCIA Resume Analysis",
        author="POTENCIA",
        subject=filename,
    )

    scores = report.get("scores") or {}
    ats = report.get("ats") or {}
    findings = report.get("findings") or []
    strengths = report.get("strengths") or []
    actions = report.get("priority_actions") or []

    story: list[Any] = [
        Paragraph("POTENCIA", style["title"]),
        Paragraph("Beyond Your Resume. Unleash Your Potential.", style["subtitle"]),
        Spacer(1, 8),
        Paragraph(escape(filename), style["h2"]),
        Paragraph(
            f"Generated {generated_at.strftime('%d %B %Y, %H:%M UTC')} · "
            f"Scoring methodology v{escape(str(scores.get('methodology_version', '—')))}",
            style["small"],
        ),
        Spacer(1, 6),
    ]

    overall = scores.get("overall")
    band = str(scores.get("band", "—"))
    headline = Table(
        [
            [
                Paragraph(f"{overall:.1f}" if isinstance(overall, (int, float)) else "—", style["score"]),
                Paragraph(
                    f"<b><font color='#{BAND_COLORS.get(band, INK).hexval()[-6:]}'>"
                    f"{escape(band.title())}</font></b><br/>"
                    f"Overall resume score out of 100<br/>"
                    f"Applicable weight {scores.get('applicable_weight', 0)} of 100",
                    style["body"],
                ),
            ]
        ],
        colWidths=[60 * mm, 110 * mm],
    )
    headline.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F5F3FF")),
                ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.append(headline)

    components = scores.get("components") or {}
    if components:
        story.append(Paragraph("Score breakdown", style["h2"]))
        widths = [55 * mm, 25 * mm, 20 * mm, 35 * mm, 30 * mm]
        rows: list[list[Any]] = [
            [Paragraph(escape(label), style["cell"]) for label in ("Category", "Score", "Weight", "Contribution", "Confidence")]
        ]
        labels = {
            "content_quality": "Content quality",
            "experience": "Experience & achievements",
            "skills": "Skills presentation",
            "structure": "Structure & organisation",
            "ats_compatibility": "ATS compatibility",
            "language_readability": "Language & readability",
        }
        for key, component in components.items():
            value = float(component.get("value", 0.0))
            weight = int(component.get("weight", 0))
            rows.append(
                [
                    Paragraph(escape(labels.get(key, key)), style["cell"]),
                    Paragraph(f"{value:.1f}", style["cell"]),
                    Paragraph(str(weight), style["cell"]),
                    Paragraph(f"{value * weight / 100:.1f}", style["cell"]),
                    Paragraph(escape(str(component.get("confidence", "—"))), style["cell"]),
                ]
            )
        table = Table(rows, colWidths=widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, RULE),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFE")]),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)

    if ats:
        story.append(Paragraph("ATS compatibility estimate", style["h2"]))
        summary = ats.get("summary") or {}
        story.append(
            Paragraph(
                f"Estimate <b>{float(ats.get('estimate', 0)):.1f} / 100</b> · "
                f"{summary.get('pass', 0)} pass · {summary.get('warn', 0)} warn · "
                f"{summary.get('fail', 0)} fail",
                style["body"],
            )
        )
        story.append(Spacer(1, 4))
        checks = ats.get("checks") or []
        if checks:
            rows = [
                [
                    Paragraph("Check", style["cell_head"]),
                    Paragraph("Status", style["cell_head"]),
                    Paragraph("What to do", style["cell_head"]),
                ]
            ]
            for check in checks:
                rows.append(
                    [
                        Paragraph(escape(str(check.get("label", ""))), style["cell"]),
                        Paragraph(escape(str(check.get("status", ""))).upper(), style["cell"]),
                        Paragraph(escape(str(check.get("remediation", ""))), style["cell"]),
                    ]
                )
            table = Table(rows, colWidths=[55 * mm, 20 * mm, 95 * mm], repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(table)
        story.append(Spacer(1, 3))
        story.append(Paragraph(escape(str(ats.get("disclaimer", ""))), style["small"]))

    if actions:
        story.append(Paragraph("Priority actions", style["h2"]))
        story.append(_bullets([str(action) for action in actions], style))

    if findings:
        story.append(Paragraph("Findings and evidence", style["h2"]))
        rows = [
            [
                Paragraph("Severity", style["cell_head"]),
                Paragraph("Finding", style["cell_head"]),
                Paragraph("Evidence", style["cell_head"]),
                Paragraph("Points", style["cell_head"]),
            ]
        ]
        for finding in findings:
            evidence = "; ".join(
                escape(str(item.get("text", ""))) for item in (finding.get("evidence") or [])
            )
            rows.append(
                [
                    Paragraph(escape(str(finding.get("severity", "")).upper()), style["cell"]),
                    Paragraph(
                        f"<b>{escape(str(finding.get('title', '')))}</b><br/>"
                        f"<font size=7 color='#5A5A6E'>{escape(str(finding.get('criterion', '')))}</font>",
                        style["cell"],
                    ),
                    Paragraph(evidence or "—", style["cell"]),
                    Paragraph(_money_fmt(finding.get("score_impact")), style["cell"]),
                ]
            )
        table = Table(rows, colWidths=[22 * mm, 58 * mm, 68 * mm, 22 * mm], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, RULE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)

    if strengths:
        story.append(Paragraph("Strengths", style["h2"]))
        story.append(_bullets([str(item.get("text", "")) for item in strengths], style))

    story.append(Spacer(1, 10))
    story.append(
        Paragraph(
            "Scores are produced by deterministic rules (methodology "
            f"v{escape(str(scores.get('methodology_version', '—')))}), not by a language model. "
            "Weights are product-design hypotheses pending calibration against a "
            "reviewed dataset. The ATS figure is a compatibility estimate, not a "
            "prediction of any employer's screening outcome.",
            style["small"],
        )
    )

    document.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 10 * mm, "POTENCIA · Resume Intelligence")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(RULE)
    canvas.line(18 * mm, 13 * mm, A4[0] - 18 * mm, 13 * mm)
    canvas.restoreState()


# --------------------------------------------------------------------------- #
# Improved resume                                                              #
# --------------------------------------------------------------------------- #


def _experience_block(structure: ResumeStructure, style: dict) -> list[Any]:
    flow: list[Any] = []
    for role in structure.experience:
        header = " · ".join(filter(None, [role.title, role.organisation]))
        dates = " – ".join(filter(None, [role.start, role.end or ("Present" if role.start else None)]))
        line = escape(header) if header else "Role"
        flow.append(
            KeepTogether(
                [
                    Paragraph(line, style["role"]),
                    Paragraph(escape(dates), style["small"]),
                ]
            )
        )
        if role.bullets:
            flow.append(_bullets([bullet.text for bullet in role.bullets], style))
        flow.append(Spacer(1, 6))
    return flow


def render_resume_pdf(structure: ResumeStructure) -> bytes:
    """A clean, single-column resume — the layout an ATS parses most reliably."""
    style = _styles()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Resume",
        author=structure.contact.name or "POTENCIA user",
    )

    contact = structure.contact
    story: list[Any] = []
    if contact.name:
        story.append(Paragraph(escape(contact.name), style["name"]))
    details = " | ".join(
        filter(None, [contact.email, contact.phone, ", ".join(contact.links)])
    )
    if details:
        story.append(Paragraph(escape(details), style["small"]))
    story.append(Spacer(1, 8))

    def section(title: str) -> None:
        story.extend(
            [
                Paragraph(escape(title.upper()), style["h2"]),
                Table([[""]], colWidths=[174 * mm], rowHeights=[1],
                      style=TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.6, RULE)])),
            ]
        )

    if structure.summary.present and structure.summary.text:
        section("Professional summary")
        story.append(Paragraph(escape(structure.summary.text), style["body"]))

    if structure.experience:
        section("Experience")
        story.extend(_experience_block(structure, style))

    if structure.projects:
        section("Projects")
        for project in structure.projects:
            flow: list[Any] = [Paragraph(escape(project.name or "Project"), style["role"])]
            if project.description:
                flow.append(Paragraph(escape(project.description), style["body"]))
            story.append(KeepTogether(flow))
            if project.bullets:
                story.append(_bullets([bullet.text for bullet in project.bullets], style))
            if project.technologies:
                story.append(
                    Paragraph(
                        f"<font size=8 color='#5A5A6E'>Technologies: "
                        f"{escape(', '.join(project.technologies))}</font>",
                        style["small"],
                    )
                )
            story.append(Spacer(1, 5))

    if structure.education:
        section("Education")
        for entry in structure.education:
            headline = ", ".join(filter(None, [entry.degree, entry.field]))
            story.append(Paragraph(escape(headline or entry.institution or "Education"), style["role"]))
            meta = " · ".join(
                filter(None, [entry.institution, "-".join(filter(None, [entry.start, entry.end]))])
            )
            if meta:
                story.append(Paragraph(escape(meta), style["small"]))
            for detail in entry.details:
                story.append(Paragraph(escape(detail), style["small"]))
            story.append(Spacer(1, 5))

    if structure.skills.explicit or structure.skills.inferred:
        section("Skills")
        if structure.skills.explicit:
            story.append(Paragraph(escape(", ".join(structure.skills.explicit)), style["body"]))

    if structure.certifications:
        section("Certifications")
        story.append(
            _bullets(
                [
                    " — ".join(filter(None, [entry.name, entry.issuer, entry.date]))
                    for entry in structure.certifications
                ],
                style,
            )
        )

    if structure.achievements:
        section("Achievements")
        story.append(_bullets(structure.achievements, style))

    if structure.leadership:
        section("Leadership")
        story.append(_bullets(structure.leadership, style))

    document.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def render_resume_docx(structure: ResumeStructure) -> bytes:
    """The same resume as an editable Word document."""
    from docx import Document as DocxDocument
    from docx.shared import Pt

    document = DocxDocument()
    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10)

    contact = structure.contact
    if contact.name:
        heading = document.add_paragraph()
        run = heading.add_run(contact.name)
        run.bold = True
        run.font.size = Pt(18)

    details = " | ".join(
        filter(None, [contact.email, contact.phone, ", ".join(contact.links)])
    )
    if details:
        document.add_paragraph(details)

    def section(title: str) -> None:
        heading = document.add_heading(title.upper(), level=2)
        for run in heading.runs:
            run.font.size = Pt(11)

    if structure.summary.present and structure.summary.text:
        section("Professional summary")
        document.add_paragraph(structure.summary.text)

    if structure.experience:
        section("Experience")
        for role in structure.experience:
            line = document.add_paragraph()
            run = line.add_run(" · ".join(filter(None, [role.title, role.organisation])))
            run.bold = True
            dates = " – ".join(
                filter(None, [role.start, role.end or ("Present" if role.start else None)])
            )
            if dates:
                document.add_paragraph(dates)
            for bullet in role.bullets:
                document.add_paragraph(bullet.text, style="List Bullet")

    if structure.projects:
        section("Projects")
        for project in structure.projects:
            line = document.add_paragraph()
            line.add_run(project.name or "Project").bold = True
            if project.description:
                document.add_paragraph(project.description)
            for bullet in project.bullets:
                document.add_paragraph(bullet.text, style="List Bullet")
            if project.technologies:
                document.add_paragraph(f"Technologies: {', '.join(project.technologies)}")

    if structure.education:
        section("Education")
        for entry in structure.education:
            line = document.add_paragraph()
            line.add_run(", ".join(filter(None, [entry.degree, entry.field])) or "Education").bold = True
            meta = " · ".join(
                filter(None, [entry.institution, "-".join(filter(None, [entry.start, entry.end]))])
            )
            if meta:
                document.add_paragraph(meta)
            for detail in entry.details:
                document.add_paragraph(detail)

    if structure.skills.explicit:
        section("Skills")
        document.add_paragraph(", ".join(structure.skills.explicit))

    if structure.certifications:
        section("Certifications")
        for entry in structure.certifications:
            document.add_paragraph(
                " — ".join(filter(None, [entry.name, entry.issuer, entry.date])),
                style="List Bullet",
            )

    if structure.achievements:
        section("Achievements")
        for item in structure.achievements:
            document.add_paragraph(item, style="List Bullet")

    if structure.leadership:
        section("Leadership")
        for item in structure.leadership:
            document.add_paragraph(item, style="List Bullet")

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
