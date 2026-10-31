"""Measure the running API and regenerate the README charts.

Every number in the README comes from this script, run against a live instance.
It uploads one generated resume, analyses it repeatedly, exports documents and
records the latencies it actually observed. Nothing here is illustrative: if the
API is slower, the chart is slower.

    python scripts/readme_metrics.py --base http://localhost:8010

Charts land in `assets/readme/`; the raw measurements go to
`assets/readme/metrics.json`.
"""

from __future__ import annotations

import argparse
import io
import json
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pymupdf  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "readme"

INK = "#12121A"
MUTED = "#5A5A6E"
GRID = "#E3E3EC"
ACCENT = "#6D3BF5"
CYAN = "#22D3EE"

RESUME = """ARJUN MEHTA
arjun.mehta@example.com | +91 98765 43210 | linkedin.com/in/arjunmehta

SUMMARY
Backend engineer with four years building payment services.

TECHNICAL SKILLS
Python, Django, PostgreSQL, Docker, AWS, Kubernetes, Redis

WORK EXPERIENCE
Backend Engineer
Acme Payments | Mar 2022 - Present
- Built a ledger service handling 2M daily transactions
- Worked on latency improvements
- Responsible for mentoring

Software Engineer
Northwind Systems | Jul 2020 - Feb 2022
- Automated reconciliation reports with Python and Pandas

EDUCATION
B.Tech in Computer Science
National Institute of Technology | 2016 - 2020
"""

JOB = """Senior Backend Engineer
Requirements:
We need 5+ years of Python experience, PostgreSQL, Kubernetes and Terraform.
Nice to have: Kafka, GraphQL.
Responsibilities:
Own the payment ledger service and mentor engineers.
Bachelor's degree in Computer Science required.
"""


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.token: str | None = None

    def call(self, method: str, path: str, payload: dict | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        started = time.perf_counter()
        with urllib.request.urlopen(request) as response:
            body = response.read()
            elapsed = (time.perf_counter() - started) * 1000
        return (json.loads(body) if body else None), elapsed

    def upload(self, filename: str, data: bytes):
        boundary = "----potencia"
        head = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            "Content-Type: application/pdf\r\n\r\n"
        ).encode()
        body = head + data + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(
            self.base + "/api/v1/resumes",
            data=body,
            method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Authorization": f"Bearer {self.token}",
            },
        )
        started = time.perf_counter()
        with urllib.request.urlopen(request) as response:
            parsed = json.loads(response.read())
        return parsed, (time.perf_counter() - started) * 1000


def sample_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(40, 40, 555, 800), RESUME, fontsize=9)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def style(ax) -> None:
    ax.set_facecolor("white")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.6)


def bar_chart(labels: list[str], values: list[float], title: str, name: str, color: str) -> None:
    figure, ax = plt.subplots(figsize=(8.0, 3.4), dpi=200)
    positions = range(len(labels))
    ax.bar(positions, values, color=color, width=0.55)
    ax.set_xticks(list(positions), labels, fontsize=8, color=INK, rotation=0)
    ax.set_ylim(0, max(100, max(values) * 1.15))
    ax.set_title(title, fontsize=9, color=INK, loc="left")
    style(ax)
    for position, value in zip(positions, values, strict=True):
        ax.text(position, value + 2, f"{value:.1f}", ha="center", fontsize=7, color=MUTED)
    figure.tight_layout()
    figure.savefig(OUT / name, transparent=False, facecolor="white")
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8010")
    parser.add_argument("--runs", type=int, default=20)
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    api = Api(args.base)
    email = f"metrics{int(time.time())}@example.com"
    api.token = api.call(
        "POST", "/api/v1/auth/register", {"email": email, "password": "a-long-enough-password"}
    )[0]["tokens"]["access_token"]

    resume, upload_ms = api.upload("arjun.pdf", sample_pdf())
    analysis, first_analysis_ms = api.call("POST", "/api/v1/analyses", {"resume_id": resume["id"]})

    analysis_times: list[float] = []
    for _ in range(args.runs):
        _, elapsed = api.call("POST", "/api/v1/analyses", {"resume_id": resume["id"]})
        analysis_times.append(elapsed)

    export_times: list[float] = []
    for _ in range(args.runs):
        record, elapsed = api.call(
            "POST", "/api/v1/exports", {"analysis_id": analysis["id"], "kind": "analysis_report", "format": "pdf"}
        )
        export_times.append(elapsed)

    recommendations, recs_ms = api.call("GET", f"/api/v1/analyses/{analysis['id']}/recommendations")
    job, _ = api.call("POST", "/api/v1/jobs", {"title": "Senior Backend Engineer", "description": JOB})
    match, match_ms = api.call("POST", "/api/v1/matches", {"resume_id": resume["id"], "job_id": job["id"]})

    scores = analysis["scores"]
    components = scores["components"]
    order = [
        "content_quality",
        "experience",
        "skills",
        "structure",
        "ats_compatibility",
        "language_readability",
    ]
    labels = [
        "Content",
        "Experience",
        "Skills",
        "Structure",
        "ATS",
        "Language",
    ]
    values = [components[key]["value"] for key in order]

    bar_chart(labels, values, "Category scores for the sample resume", "score-breakdown.png", ACCENT)

    severity_order = ["critical", "high", "medium", "low", "info"]
    counts = {level: sum(1 for finding in analysis["findings"] if finding["severity"] == level) for level in severity_order}
    figure, ax = plt.subplots(figsize=(7.2, 2.6), dpi=200)
    ax.barh(
        list(reversed(severity_order)),
        [counts[level] for level in reversed(severity_order)],
        color=["#94A3B8", "#FACC15", "#FB923C", "#F87171", "#DC2626"],
        height=0.55,
    )
    ax.set_title("Findings by severity", fontsize=9, color=INK, loc="left")
    style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    figure.tight_layout()
    figure.savefig(OUT / "findings.png", facecolor="white")
    plt.close(figure)

    figure, ax = plt.subplots(figsize=(7.2, 3.0), dpi=200)
    ax.plot(range(1, len(analysis_times) + 1), analysis_times, color=ACCENT, linewidth=1.4, marker="o", markersize=2.5)
    ax.axhline(statistics.median(analysis_times), color=CYAN, linestyle="--", linewidth=1)
    ax.set_xlabel("run", fontsize=8, color=MUTED)
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    ax.set_ylabel("ms", fontsize=8, color=MUTED)
    ax.set_title("Analysis latency, full pipeline", fontsize=9, color=INK, loc="left")
    style(ax)
    figure.tight_layout()
    figure.savefig(OUT / "latency.png", facecolor="white")
    plt.close(figure)

    metrics = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sample": {
            "word_count": resume["structure"]["word_count"],
            "roles": len(resume["structure"]["experience"]),
            "bullets": resume["structure"]["bullet_count"],
            "explicit_skills": len(resume["structure"]["skills"]["explicit"]),
            "overall": scores["overall"],
            "band": scores["band"],
            "ats": analysis["ats"]["estimate"],
            "findings": len(analysis["findings"]),
            "priority_actions": len(analysis["priority_actions"]),
            "recommendations": len(recommendations),
            "match_estimate": match["result"]["estimate"],
            "gaps": [gap["name"] for gap in match["result"]["gaps"]],
            "components": {key: components[key]["value"] for key in order},
            "severity": counts,
        },
        "latency_ms": {
            "upload": round(upload_ms, 1),
            "analysis_first": round(first_analysis_ms, 1),
            "analysis_p50": round(statistics.median(analysis_times), 1),
            "analysis_p95": round(sorted(analysis_times)[max(0, int(len(analysis_times) * 0.95) - 1)], 1),
            "recommendations": round(recs_ms, 1),
            "match": round(match_ms, 1),
            "export_p50": round(statistics.median(export_times), 1),
            "export_max": round(max(export_times), 1),
        },
        "runs": args.runs,
    }
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
