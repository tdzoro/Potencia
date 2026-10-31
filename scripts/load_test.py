"""Measure the analysis endpoint under real concurrent load.

    python scripts/load_test.py --workers 8 --requests 200

Each worker registers an account, uploads one document, then posts analyses. The
document is parsed and scored for real — nothing is stubbed — so the latency
numbers include PDF extraction, the parser and the scoring engine.

Rate limiting must be off for a meaningful measurement (`POTENCIA_RATE_LIMIT_ENABLED=false`),
because otherwise the run measures the throttle: 20 analyses per hour per
account. The script says so in its output and refuses to guess.

What this is not: a capacity plan. It runs on one host against one database with
a few hundred requests, which is enough to catch a regression in the engine's
cost and not enough to promise production throughput.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fitz
import httpx

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "assets" / "readme" / "load.json"

RESUME_TEXT = """ANANYA SHARMA
ananya.sharma@example.com | +91 98765 43210 | github.com/ananyas

SUMMARY
Backend engineer with 4 years building payment and billing services in Python.

TECHNICAL SKILLS
Python, FastAPI, PostgreSQL, Redis, Docker, Kubernetes, AWS, Terraform

WORK EXPERIENCE
Senior Backend Engineer
Northwind Pay | Mar 2022 - Present
- Built a ledger service handling 2M daily transactions with zero data loss
- Reduced p99 latency from 800ms to 220ms by adding a Redis read-through cache
- Led a four-engineer migration to Terraform, cutting deploy time by 60%

Backend Engineer
Cloudline | Jul 2020 - Feb 2022
- Designed idempotent payment retries, reducing duplicate charges by 94%
- Wrote 320 integration tests, raising coverage of the billing module to 88%

PROJECTS
Open Ledger
- Open-source double-entry ledger used by 3 companies
- Implemented Postgres advisory locking to keep balances consistent

EDUCATION
B.Tech in Computer Science
National Institute of Technology | 2016 - 2020

CERTIFICATIONS
AWS Certified Solutions Architect - Associate | 2023
"""


def _pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(fitz.Rect(40, 40, 555, 800), RESUME_TEXT, fontsize=9)
    data = document.tobytes()
    document.close()
    return data


def _register(client: httpx.Client, base_url: str, index: int) -> str:
    email = f"load-{uuid.uuid4().hex[:10]}-{index}@example.com"
    response = client.post(
        f"{base_url}/api/v1/auth/register",
        json={"email": email, "password": "a-long-enough-password", "display_name": "Load"},
    )
    response.raise_for_status()
    return response.json()["tokens"]["access_token"]


def _upload(client: httpx.Client, base_url: str, token: str, data: bytes) -> str:
    response = client.post(
        f"{base_url}/api/v1/resumes",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("load.pdf", data, "application/pdf")},
    )
    response.raise_for_status()
    return response.json()["id"]


def _worker(
    base_url: str, pdf: bytes, index: int, per_worker: int, timeout: float
) -> tuple[list[float], list[int]]:
    latencies: list[float] = []
    failures: list[int] = []
    with httpx.Client(timeout=timeout) as client:
        token = _register(client, base_url, index)
        resume_id = _upload(client, base_url, token, pdf)
        headers = {"Authorization": f"Bearer {token}"}
        for _ in range(per_worker):
            started = time.perf_counter()
            response = client.post(
                f"{base_url}/api/v1/analyses", headers=headers, json={"resume_id": resume_id}
            )
            latencies.append((time.perf_counter() - started) * 1000.0)
            if response.status_code != 201:
                failures.append(response.status_code)
    return latencies, failures


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser(description="Load test the POTENCIA analysis endpoint.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    per_worker, remainder = divmod(args.requests, args.workers)
    counts = [per_worker + (1 if index < remainder else 0) for index in range(args.workers)]
    pdf = _pdf_bytes()

    print(
        f"{args.requests} analyses over {args.workers} concurrent clients against {args.base_url}"
    )
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(
            pool.map(
                lambda pair: _worker(args.base_url, pdf, pair[0], pair[1], args.timeout),
                list(enumerate(counts)),
            )
        )
    elapsed = time.perf_counter() - started

    latencies = [value for chunk, _ in results for value in chunk]
    failures = [status for _, chunk in results for status in chunk]

    if not latencies:
        raise SystemExit("no requests completed")

    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url": args.base_url,
        "workers": args.workers,
        "requests_completed": len(latencies),
        "requests_failed": len(failures),
        "failure_statuses": sorted(set(failures)),
        "wall_seconds": round(elapsed, 3),
        "throughput_rps": round(len(latencies) / elapsed, 2),
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 1),
            "p50": round(_percentile(latencies, 0.50), 1),
            "p95": round(_percentile(latencies, 0.95), 1),
            "p99": round(_percentile(latencies, 0.99), 1),
            "max": round(max(latencies), 1),
        },
        "python": platform.python_version(),
        "note": (
            "Single host, single API process, local PostgreSQL. Rate limiting disabled so the "
            "measurement covers parsing and scoring rather than the throttle. Not a capacity plan."
        ),
    }

    print(
        "\n".join(
            [
                f"completed   {summary['requests_completed']} ({summary['requests_failed']} failed)",
                f"wall        {summary['wall_seconds']} s",
                f"throughput  {summary['throughput_rps']} analyses/s",
                f"latency     p50 {summary['latency_ms']['p50']} ms · "
                f"p95 {summary['latency_ms']['p95']} ms · "
                f"p99 {summary['latency_ms']['p99']} ms · max {summary['latency_ms']['max']} ms",
            ]
        )
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
