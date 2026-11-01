<div align="center">

<img src="assets/brand/potencia-logo.png" alt="POTENCIA" width="720" />

### Beyond Your Resume. Unleash Your Potential.

**AI Resume Intelligence — explainable scoring, ATS compatibility, job matching, and edits you approve.**

[![Tests](https://img.shields.io/badge/tests-150%20backend%20·%2011%20browser-6D3BF5?style=flat-square)](docs/TESTING.md)
[![API](https://img.shields.io/badge/API-32%20operations-22D3EE?style=flat-square)](docs/API.md)
[![Methodology](https://img.shields.io/badge/scoring-v1.0.0-8B5CF6?style=flat-square)](docs/SCORING_METHODOLOGY.md)
[![Licence](https://img.shields.io/badge/licence-proprietary-9AA3C7?style=flat-square)](LICENSE)

</div>

---

## The premise

Every resume tool tells you a number. Almost none can tell you where the number came from, and fewer still will refuse to make one up.

POTENCIA is built on a single constraint: **the score is arithmetic over evidence, not an opinion**. A rule set reads the document, extracts what is actually there, measures 27 criteria, and reports the sentence that caused each deduction. The same document always produces the same score — not because it is cached, but because nothing random is in the path.

| | What it answers | How |
|:--|:--|:--|
| **01** | How strong is this resume? | 27 weighted criteria across 6 categories |
| **02** | Will software be able to read it? | Structural ATS compatibility estimate, with hazards named |
| **03** | How well does it fit *this* job? | Requirement extraction, then three-state skill matching |
| **04** | What exactly should change? | Prioritised findings, each with a quoted line and a fix |

---

## Proof, not adjectives

One resume — 87 words, 2 roles, 4 bullets, 7 listed skills — run through the finished pipeline against PostgreSQL. Every figure below is produced by `scripts/readme_metrics.py` and stored in [`assets/readme/metrics.json`](assets/readme/metrics.json).

<table>
<tr>
<td width="50%" valign="top">

**What the parser recovered**

| Field | Value |
|:--|--:|
| Words / bullets | 87 / 4 |
| Experience entries | 2 |
| Explicit skills | 7 |
| Inferred skills | 1 |
| Extraction method | text layer |
| Extraction confidence | 0.97 |

</td>
<td width="50%" valign="top">

**What the engines concluded**

| Metric | Value |
|:--|--:|
| Overall score | **82.6** / 100 |
| Band | strong |
| ATS compatibility | **88.2** / 100 |
| Findings raised | 13 |
| Priority actions | 5 |
| Recommendations | 13 |
| Job match | **49.0** / 100 |

</td>
</tr>
</table>

The report reconciles with itself: the 13 findings' impacts sum to **17.4 points**, which is exactly `100 − 82.6`. That identity is a test, not a claim — if the findings stop explaining the score, the suite fails.

---

## Scoring: the formula, and why it is legible

```
overall = Σ ( category_score × weight ) / Σ ( weight of applicable categories )
```

| Category | Weight | Score | Contribution |
|:--|--:|--:|--:|
| Content quality | 25 | 78.4 | 19.60 |
| Experience & achievements | 20 | 86.9 | 17.38 |
| Structure & organisation | 15 | 100.0 | 15.00 |
| ATS compatibility | 15 | 88.2 | 13.23 |
| Skills presentation | 15 | 66.2 | 9.93 |
| Language & readability | 10 | 74.5 | 7.45 |
| **Total** | **100** | | **82.59 → 82.6** |

Two rules do the heavy lifting:

1. **Missing is not zero.** A section that does not apply leaves the denominator instead of scoring 0 — a fresher is not penalised for having no employment history, and every report states the applicable weight (here 100 of 100).
2. **Every deduction cites text.** A criterion that fires must attach a verbatim excerpt. A finding without evidence is a bug, and the API refuses to serialise one.

![Category scores](assets/readme/score-breakdown.png)

---

## Are the weights defensible? A harness, not a claim

`scripts/calibrate.py` parses eight fixtures with the real parser, scores them with the real engine, and measures whether each candidate weight vector ranks them the way the rubric did.

| Candidate | Spearman | Pairwise | Tier spread |
|:--|--:|--:|--:|
| **shipped (v1.0.0)** | **0.909** | **0.920** | **39.4** |
| content-heavy | 0.873 | 0.880 | 40.7 |
| ats-heavy | 0.909 | 0.920 | 34.3 |
| experience-heavy | 0.873 | 0.880 | 37.7 |
| equal-weights | 0.909 | 0.920 | 40.8 |

No alternative beats the shipped vector, so the weights stay — and now the claim is reproducible rather than asserted. This is still **not** an empirical validation: the tiers are rubric-assigned fixtures, not recruiter rankings. Result stored in [`assets/readme/calibration.json`](assets/readme/calibration.json).

---

## Findings: severity is a work queue

![Findings by severity](assets/readme/findings.png)

13 findings: **2 high, 6 medium, 5 low**. Impact-ordered, not severity-ordered, so the first action buys the most points. Each carries the excerpt that triggered it, an explanation, and a remediation.

---

## Matching: three states, never two

A skill in a job description has three possible positions relative to a resume. Most tools collapse them into two and end up telling people to add skills they already have.

```mermaid
flowchart LR
    A[Skill in job description] --> B{In resume at all?}
    B -- no --> C[<b>absent</b><br/>Not present anywhere]
    B -- yes --> D{Claimed in the skills list?}
    D -- yes --> E{Used in a role or project?}
    E -- yes --> F[<b>matched</b><br/>Claimed and demonstrated]
    E -- no --> G[<b>partial</b><br/>Claimed, never shown]
    D -- no --> H[<b>weakly demonstrated</b><br/>Shown, never claimed]
```

On the sample job description:

| Requirement | Status | Meaning in the report |
|:--|:--|:--|
| Python | matched | Listed *and* used in a bullet |
| PostgreSQL | partial | Listed, never demonstrated |
| Kubernetes | partial | Listed, never demonstrated |
| Terraform | absent | Nowhere in the document |
| Kafka | absent | Nowhere in the document |
| GraphQL *(preferred)* | absent | Nowhere in the document |

The match is **49.0**, which reads low — and it should. The candidate claims seven technologies and demonstrates one. That is the finding, not a bug: an unevidenced claim is worth less than a visible gap, so the gap advice says *"do not add it unless you have genuinely used it."*

---

## ATS compatibility: an estimate, stated as one

The ATS figure separates **document parseability** from **job keyword relevance** — two different questions that tools routinely merge into one misleading number.

Checks cover text-layer extraction, reading order, tables and columns, headers and footers, heading clarity, contact extractability, date consistency and non-standard glyphs. Every check reports `pass` / `warn` / `fail` with evidence and a correction. The estimate **88.2** reflects a clean single-column text-layer PDF, and the disclaimer travels with it in the API, the report and the PDF:

> ATS compatibility estimate. Not a prediction of screening outcomes.

---

## Recommendations that ask instead of invent

The engine produces 13 recommendations from 13 findings: 3 concrete rewrites, 4 that ask the user for a fact, and the rest structural fixes with a stated next step.

| Situation | What POTENCIA does | What it will never do |
|:--|:--|:--|
| Bullet has no metric | Asks *"What scale did this work operate at — records, requests per day, users, revenue, or time saved? Give the real figure."* | Insert a plausible number |
| Weak opener ("Responsible for…") | Proposes "Owned …" | Invent scope |
| Skill claimed, never used | Points at the gap and asks which role used it | Add a project |
| Anything factual | Requires your click in the Improvement Studio | Auto-replace your resume |

The original parse is **revision 0** and is never overwritten. An edit is a new node pointing at its parent, so history is a tree you can always walk back.

---

## Reliability that is enforced, not aspirational

| Concern | Behaviour |
|:--|:--|
| Double submits | `X-Idempotency-Key` replays the original response for 24h; reusing a key on another endpoint is `409` |
| Paging | Keyset cursors on UUIDv7 — new rows arriving mid-walk never duplicate or skip a record |
| Cross-worker limits | Redis-backed counters when `POTENCIA_REDIS_URL` is set; process memory otherwise, logged at startup |
| Downloads | HMAC-signed, account-bound, 15-minute capability URLs |
| Retention | Exports expire in 24h; a scheduled `app.tasks.retention` service deletes the files and rows — the promise is performed, not just printed |
| Versions | One resume, several named versions (`label`), each a full snapshot; any two compare field by field, and any one can be exported by name |

---

## Latency, measured on a local PostgreSQL container

![Analysis latency](assets/readme/latency.png)

| Stage | p50 | p95 / max |
|:--|--:|--:|
| Upload + parse | 19.7 ms | — |
| Analysis (parse → score → ATS → findings) | 14.5 ms | 16.7 ms |
| Recommendations | 30.1 ms | — |
| Job match | 16.8 ms | — |
| PDF export | 54.5 ms | 64.9 ms |

30 runs each, single user. These are **request** latencies, not engine cost: authentication, JSON, PostgreSQL and HTTP are in the same number, and they move by tens of percent between runs on a shared machine — one earlier run of the same script put analysis at 25.4 ms. The controlled measurement is the engine profile below.

Under concurrency — `scripts/load_test.py`, 8 clients, 200 analyses, limiter disabled so the run measures the engines rather than the throttle:

| Metric | Value |
|:--|--:|
| Analyses completed | **200 / 200** (0 failed) |
| Wall time | 3.67 s |
| Throughput | **54.6 analyses/s** |
| Latency p50 / p95 / p99 | **99.1 / 197.0 / 228.6 ms** |
| Slowest | 251.5 ms |

One host, one API process, one local PostgreSQL. The same run measured 77.4 analyses/s earlier in the project on this machine, so the figure is a property of the host and its database state as much as of the code: it bounds cost, and it is not a capacity plan. Raw figures in [`assets/readme/load.json`](assets/readme/load.json).

### Engine cost, before and after the profile

`scripts/profile_engine.py` times the deterministic pipeline with no HTTP and no database, and it is what the last round of optimisation was based on. It found two shapes worth fixing: the heading keyword table was re-sorted **for every line** parsed, and the resume body was re-read **for every required skill** matched.

| Stage (p50, same host, same script) | Before | After | Change |
|:--|--:|--:|--:|
| Parse | 2.92 ms | **0.77 ms** | **3.8× faster** |
| Score | 1.30 ms | **0.37 ms** | 3.5× |
| Parse + score | 4.57 ms | **1.22 ms** | 3.7× |
| Job match, 12 requirements | 0.69 ms | **0.06 ms** | 11.5× |
| Job match, 40 requirements | 3.10 ms | **0.40 ms** | 7.8× |
| Full pipeline | 6.17 ms | **1.61 ms** | 3.8× |

Parsing is now linear in document size: 1.49 ms/KB at 0.8 KB and 1.05 ms/KB at 6.7 KB, where the old shape drifted upward as the text grew. The remaining hot spot is date normalisation, not the parser.

No behaviour changed with the speed. The 150-test suite, including score reconciliation and the calibration harness, produced identical scores before and after.

---

## Architecture

```mermaid
flowchart TB
    subgraph Client
        UI[React 18 · TypeScript · Tailwind<br/>Router · TanStack Query]
    end
    subgraph API["API — FastAPI"]
        R[Routes<br/>auth · resumes · analyses · jobs<br/>matches · recommendations · exports]
        S[Services<br/>ownership · orchestration · export]
        X[Cross-cutting<br/>idempotency · rate limits · pagination]
    end
    subgraph Intelligence["Intelligence — deterministic"]
        D[Document<br/>validate · extract]
        P[Parser<br/>sections · entities · confidence]
        SC[Scoring<br/>27 criteria · 6 categories]
        AT[ATS<br/>structural hazards]
        M[Matching<br/>requirements · 3-state skills]
        RC[Recommendations<br/>rules · provider seam]
    end
    DB[(PostgreSQL)]
    FS[(Content-addressed storage)]

    UI -->|JWT| R --> S
    S --> D --> P
    S --> SC
    S --> AT
    S --> M
    S --> RC
    S --> DB
    S --> FS
    X -.-> R
```

---

## Run it

```bash
git clone https://github.com/tdzoro/Potencia && cd Potencia
cp .env.example .env            # set POTENCIA_SECRET_KEY
docker compose up --build       # API on :8000, web on :8080
```

Local development:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export POTENCIA_DATABASE_URL=postgresql+psycopg://potencia:potencia@localhost:5432/potencia
export POTENCIA_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
alembic upgrade head
uvicorn app.main:app --reload
```

```bash
cd frontend && npm install && npm run dev
```

---

## API surface

32 operations across 24 paths, all under `/api/v1` except health. Full contracts in [`docs/API.md`](docs/API.md).

| Group | Operations |
|:--|:--|
| Auth | register · login · refresh · logout · me · delete account |
| Resumes | upload · list · get · revisions (list, create, compare) · delete |
| Analyses | create · list · get · report · recommendations · exports · delete |
| Jobs & matches | create · list · get · delete · match · read |
| Recommendations | decide (accept · reject · edit) |
| Exports | create · get · signed download · delete |

---

## Security posture

| Control | State |
|:--|:--|
| Password hashing | bcrypt, per-password salt |
| Tokens | 15-min access JWT, 14-day refresh, revoked by `token_version` |
| Account enumeration | Identical `401` for unknown email and wrong password |
| Data isolation | Row-level `user_id`; another user's resource returns `404` |
| Uploads | Extension + magic bytes + streaming size cap |
| Downloads | HMAC-signed, user-bound, 15-minute capability URL |
| Rate limits | Login 5/15 min · uploads 10/h · analyses 20/h · exports 30/h |
| Response headers | `nosniff` · `DENY` framing · `no-referrer` · strict CSP · `no-store` |

Full detail, including what is deliberately not implemented yet, is in [`docs/SECURITY.md`](docs/SECURITY.md).

---

## Testing

```bash
cd backend && pytest -q          # 150 tests, no database or network required
cd frontend && npm run build     # strict typecheck + production build
cd frontend && npm run e2e       # 11 browser tests against a live stack
```

The browser suite seeds its own account through the API and drives the real UI: the score is asserted from the DOM, a recommendation is accepted and re-read after reload, a PDF is generated and its signed link verified, a job description produces a named gap, a revision is saved without touching the original, a named version is compared field by field, and that same version is exported by name.

Tests that exist to stop the product lying: score reconciliation, evidence on every finding, *no digits in an invented rewrite*, `partial` never collapsing into `absent`, and revision 0 being byte-identical after an edit. Details in [`docs/TESTING.md`](docs/TESTING.md).

---

## Limitations

Stated here rather than discovered later:

- **The weights are not empirically validated.** A reproducible harness shows the shipped vector is not beaten by plausible alternatives on eight rubric-ranked fixtures; that is a floor, not a study.
- **The ATS score simulates no specific vendor.** It measures structural parseability, the honest shared denominator.
- **No LLM in the request path.** Recommendations are rules; the provider seam exists and validates any rewrite before use.
- **No OCR engine installed.** Scanned PDFs are detected and reported as `partial` with `ocr_not_performed` rather than silently scored on bad text.
- **No malware scanning** on uploads; no email verification flow.
- **Throughput is single-node and host-dependent.** The load run is 200 analyses over 8 clients against one API process; the same run has measured 54.6 and 77.4 analyses/s on this machine at different times, so no throughput claim is made. Multi-process and multi-host scaling are unmeasured.
- **Comparison covers summary, skills, experience bullets, projects and education.** Certifications, achievements and leadership lines are carried in every version and exported, but are not diffed field by field.
- **Registration is limited to 5 per 15 minutes per identity**, which a shared office IP can reach. The browser suite seeds once for that reason.

---

## Documentation

| Document | Contents |
|:--|:--|
| [SRS](docs/SRS.md) | Requirements, journeys, acceptance criteria |
| [Architecture](docs/ARCHITECTURE.md) | Modules, boundaries, sequences, data model |
| [API](docs/API.md) | Every endpoint, payload and error code |
| [Scoring methodology](docs/SCORING_METHODOLOGY.md) | All 27 criteria, weights, applicability, confidence |
| [Security](docs/SECURITY.md) | Controls, threat surface, gaps |
| [Testing](docs/TESTING.md) | Coverage and the assertions that matter |
| [Status](docs/PROJECT_STATUS.md) | Phase-by-phase state and known issues |

---

<div align="center">

**POTENCIA** · AI Resume Intelligence
Built by [Arghya Bose](https://github.com/tdzoro) · © 2026 POTENCIA Team · All rights reserved

</div>
