"""Seed a demo account with an analysed resume and a job match.

    PYTHONPATH=backend backend/.venv/bin/python scripts/seed_demo.py \
        --base http://127.0.0.1:8010

The landing page can then open a finished report for a visitor who has not
uploaded anything. The script is idempotent: it reuses the demo resume, its
analysis and the demo job when they already exist, so re-running it does not
pile up duplicates.

Only run this against an environment where you intend a shared account to be
reachable. The credentials are printed, never written to the repository.
"""

from __future__ import annotations

import argparse
import io
import json
import time
import urllib.error
import urllib.request

import pymupdf

DEMO_RESUME = """ARJUN MEHTA
arjun.mehta@example.com | +91 98765 43210 | linkedin.com/in/arjunmehta

SUMMARY
Backend engineer with four years building payment services in Python.

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

DEMO_JOB_TITLE = "Senior Backend Engineer"
DEMO_JOB = """Senior Backend Engineer
Requirements:
We need 5+ years of Python experience, PostgreSQL, Kubernetes and Terraform.
Nice to have: Kafka, GraphQL.
Responsibilities:
Own the payment ledger service and mentor engineers.
Bachelor's degree in Computer Science required.
"""


class SeedError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.token: str | None = None

    def _request(self, request: urllib.request.Request) -> dict:
        try:
            with urllib.request.urlopen(request) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            raise SeedError(exc.code, exc.read().decode(errors="replace")) from exc
        return json.loads(body) if body else {}

    def call(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return self._request(
            urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        )

    def upload(self, filename: str, data: bytes) -> dict:
        boundary = "----potencia-demo"
        head = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"{filename}\"\r\nContent-Type: application/pdf\r\n\r\n"
        ).encode()
        body = head + data + f"\r\n--{boundary}--\r\n".encode()
        return self._request(
            urllib.request.Request(
                self.base + "/api/v1/resumes",
                data=body,
                method="POST",
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Authorization": f"Bearer {self.token}",
                },
            )
        )


def resume_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(40, 40, 555, 800), DEMO_RESUME, fontsize=9)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def sign_in(api: Api, email: str, password: str) -> None:
    try:
        payload = api.call(
            "POST", "/api/v1/auth/register", {"email": email, "password": password}
        )
    except SeedError as exc:
        if exc.status != 409:
            raise
        payload = api.call("POST", "/api/v1/auth/login", {"email": email, "password": password})
    # Registration nests the pair under `tokens`; login returns it flat. Accept
    # either so a re-run after the account exists still works.
    tokens = payload.get("tokens") or payload
    api.token = tokens["access_token"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8010")
    parser.add_argument("--email", default="demo@potencia.app")
    parser.add_argument("--password", default="potencia-demo-2026")
    parser.add_argument("--display-name", default="POTENCIA Demo")
    args = parser.parse_args()

    api = Api(args.base)
    try:
        sign_in(api, args.email, args.password)
    except SeedError as exc:
        if exc.status in {401, 403}:
            print(
                "The demo account exists but cannot sign in. If email verification is "
                "required in this environment, verify the address first."
            )
        raise SystemExit(f"seed failed: {exc}") from exc

    resumes = api.call("GET", "/api/v1/resumes?limit=100")["items"]
    resume = next(
        (item for item in resumes if item["original_filename"] == "demo-resume.pdf"), None
    )
    if resume is None:
        resume = api.upload("demo-resume.pdf", resume_pdf())
        print(f"uploaded resume      {resume['id']}")
    else:
        print(f"reused resume        {resume['id']}")

    analyses = api.call("GET", "/api/v1/analyses?limit=100")["items"]
    analysis = next((item for item in analyses if item["resume_id"] == resume["id"]), None)
    if analysis is None:
        analysis = api.call("POST", "/api/v1/analyses", {"resume_id": resume["id"]})
        print(f"created analysis     {analysis['id']}")
    else:
        print(f"reused analysis      {analysis['id']}")

    jobs = api.call("GET", "/api/v1/jobs")
    job = next((item for item in jobs if item["title"] == DEMO_JOB_TITLE), None)
    if job is None:
        job = api.call(
            "POST",
            "/api/v1/jobs",
            {"title": DEMO_JOB_TITLE, "company": "Acme Payments", "description": DEMO_JOB},
        )
        print(f"created job          {job['id']}")
    else:
        print(f"reused job           {job['id']}")

    match = api.call("POST", "/api/v1/matches", {"resume_id": resume["id"], "job_id": job["id"]})
    detail = api.call("GET", f"/api/v1/analyses/{analysis['id']}/report")

    scores = detail.get("scores") or {}
    estimate = (match.get("result") or {}).get("estimate")
    print()
    print(f"demo account         {args.email} / {args.password}")
    print(f"report               overall {scores.get('overall')} ({scores.get('band')})")
    print(f"ATS estimate         {(detail.get('ats') or {}).get('estimate')}")
    print(f"job match            {match['id']} (estimate {estimate})")
    print()
    print("Frontend: build with VITE_DEMO_MODE=1 so the landing page links to /login?demo=1.")
    print("Re-running this script reuses the existing rows; it was last run at "
          f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}.")


if __name__ == "__main__":
    main()
