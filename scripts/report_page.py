"""Render page one of a real analysis report to PNG for the README.

The README shows the web UI; this shows what a user actually downloads. It seeds
an account through the API, uploads the sample resume, analyses it, requests the
PDF report and rasterises the first page with PyMuPDF. No latency figures are
re-measured here, so adding this image cannot disturb the stored measurements.

    PYTHONPATH=backend:. backend/.venv/bin/python scripts/report_page.py

Writes `assets/readme/report-first-page.png`.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

import pymupdf

from scripts.readme_metrics import RESUME

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "readme" / "report-first-page.png"
BASE = "http://127.0.0.1:8010"
RENDER_DPI = 150


def call(method: str, path: str, payload: dict | None = None, token: str | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def upload(token: str) -> dict:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(40, 40, 555, 800), RESUME, fontsize=9)
    pdf = document.tobytes()
    document.close()

    boundary = "----potencia-report"
    head = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"arjun.pdf\"\r\n"
        "Content-Type: application/pdf\r\n\r\n"
    ).encode()
    body = head + pdf + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        BASE + "/api/v1/resumes",
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def main() -> None:
    email = f"report-{int(time.time())}@example.com"
    token = call(
        "POST", "/api/v1/auth/register", {"email": email, "password": "a-long-enough-password"}
    )["tokens"]["access_token"]

    resume = upload(token)
    analysis = call("POST", "/api/v1/analyses", {"resume_id": resume["id"]}, token)
    export = call(
        "POST",
        "/api/v1/exports",
        {"analysis_id": analysis["id"], "kind": "analysis_report", "format": "pdf"},
        token,
    )

    url = export.get("download_url")
    if not url:
        raise SystemExit(f"export produced no download url: {export}")
    if url.startswith("/"):
        url = urljoin(BASE, url)
    with urllib.request.urlopen(url) as response:
        pdf = response.read()

    document = pymupdf.open(stream=pdf, filetype="pdf")
    page = document[0]
    pixmap = page.get_pixmap(dpi=RENDER_DPI, alpha=False)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(OUT)
    print(
        f"score {analysis['scores']['overall']}, {len(document)} page(s), "
        f"page 1 {pixmap.width}x{pixmap.height} -> {OUT.relative_to(ROOT)}"
    )
    document.close()


if __name__ == "__main__":
    main()
