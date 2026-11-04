<div align="center">

<img src="assets/brand/potencia-logo.png" alt="POTENCIA" width="640" />

### Beyond Your Resume. Unleash Your Potential.

**AI Resume Intelligence — deterministic scoring, ATS compatibility, job matching, and edits you approve.**

[![Tests](https://img.shields.io/badge/tests-150%20backend%20%C2%B7%2011%20browser-6D3BF5?style=flat-square)](docs/TESTING.md)
[![API](https://img.shields.io/badge/API-32%20operations-22D3EE?style=flat-square)](docs/API.md)
[![Methodology](https://img.shields.io/badge/scoring-v1.0.0-8B5CF6?style=flat-square)](docs/SCORING_METHODOLOGY.md)
[![Engine](https://img.shields.io/badge/pipeline-2.12%20ms%20p50-0EA5E9?style=flat-square)](docs/PROJECT_STATUS.md)
[![Licence](https://img.shields.io/badge/licence-proprietary-9AA3C7?style=flat-square)](LICENSE)

</div>

---

## The premise

Every resume tool gives you a number. Very few can tell you where the number came from — and fewer still will refuse to invent one.

POTENCIA is built on a single constraint: **the score is arithmetic over evidence, not an opinion.** A rule set reads the document, extracts what is genuinely there, measures 30 criteria, and quotes the line that caused each deduction. The same document always produces the same score — not because it is cached, but because nothing random is in the path.

| | The question users actually ask | What answers it |
|:--|:--|:--|
| **01** | Is this resume any good? | 30 weighted criteria across 6 categories, reconciled to the point |
| **02** | Will software even read it? | Structural ATS compatibility estimate, hazards named and ranked |
| **03** | Does it fit *this* job? | Requirement extraction, then three-state skill matching |
| **04** | What do I change first? | Findings ordered by points lost, each with a quoted line and a fix |

```mermaid
flowchart LR
    A[Upload<br/>PDF · DOCX] --> B[Extract<br/>text layer · confidence]
    B --> C[Parse<br/>sections · entities]
    C --> D[Score<br/>30 criteria]
    C --> E[ATS<br/>structural checks]
    C --> F[Match<br/>requirements]
    D --> G[Report<br/>evidence per finding]
    E --> G
    F --> G
    G --> H[Studio<br/>you approve]
    H --> I[Export<br/>PDF · DOCX]
```

---

## Inside the product

Real screens from the running application, captured by `scripts/capture_screenshots.mjs` — it seeds an account through the API, runs the whole journey, and photographs the result. Nothing is mocked.

<table>
<tr>
<td width="50%" valign="top">
<img src="assets/readme/ui-report.png" alt="Analysis report" /><br/>
<b>Report.</b> Overall score, category breakdown, ATS estimate and the priority queue — every deduction carrying its source line.
</td>
<td width="50%" valign="top">
<img src="assets/readme/ui-dashboard.png" alt="Dashboard" /><br/>
<b>Dashboard.</b> What the last analysis concluded, with the next action already chosen.
</td>
</tr>
<tr>
<td width="50%" valign="top">
<img src="assets/readme/ui-match.png" alt="Job matching" /><br/>
<b>Job matching.</b> Partial is its own state: claimed in the skills list, never demonstrated in a role.
</td>
<td width="50%" valign="top">
<img src="assets/readme/ui-studio.png" alt="Improvement studio" /><br/>
<b>Studio.</b> Edit summary, bullets, skills, projects and education; a save is a new revision, never an overwrite.
</td>
</tr>
</table>

<details>
<summary><b>More screens — recommendations, export, history, landing</b></summary>

<table>
<tr>
<td width="50%" valign="top"><img src="assets/readme/ui-recommendations.png" alt="Recommendations" /><br/><b>Recommendations.</b> Rewrites where the text supports one, questions where it does not.</td>
<td width="50%" valign="top"><img src="assets/readme/ui-export.png" alt="Export" /><br/><b>Export.</b> Choose the version, generate a PDF or DOCX, download through a signed 15-minute URL.</td>
</tr>
<tr>
<td width="50%" valign="top"><img src="assets/readme/ui-history.png" alt="History" /><br/><b>History.</b> Uploaded resumes and their analyses, newest first with keyset cursors.</td>
<td width="50%" valign="top"><img src="assets/readme/ui-landing.png" alt="Landing" /><br/><b>Landing.</b> The commitments, stated before the product asks for a file.</td>
</tr>
</table>

</details>

---

## What you actually download

<img src="assets/readme/report-first-page.png" alt="First page of the generated PDF analysis report" width="680" />

The PDF is not a screenshot of the app. It is rendered from the stored analysis — scores, the weights behind them, the ATS checks and the finding queue — and the improved resume renders through the same layout as PDF and DOCX.

| Export | Format | Built from |
|:--|:--|:--|
| Analysis report | PDF | the stored analysis, its findings and ATS checks |
| Improved resume | PDF / DOCX | the newest approved revision, or a version you pick by name |
| Version comparison | inline | any two revisions, field by field |

Every generated document is re-opened by a parser in the test suite and searched for the score and content it claims to contain — "a file was created" is not the same as "the file is correct".

---

## Proof, not adjectives

One resume — 87 words, 2 roles, 4 bullets, 7 listed skills — through the finished pipeline against PostgreSQL. Every figure is produced by `scripts/readme_metrics.py` and stored in [`assets/readme/metrics.json`](assets/readme/metrics.json).

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
| Overall score | **82.6** / 100 |
| Band | strong |

</td>
<td width="50%" valign="top">

**What the engines concluded**

| Metric | Value |
|:--|--:|
| ATS compatibility | **88.2** / 100 |
| Findings raised | 13 |
| Priority actions | 5 |
| Recommendations | 13 |
| Job match | **49.0** / 100 |
| High / medium / low findings | 2 / 6 / 5 |
| Criteria measured | 30 |

</td>
</tr>
</table>

The report reconciles with itself: the 13 findings' impacts sum to **17.4 points**, which is exactly `100 − 82.6`. That identity is a test, not a claim — if the findings stop explaining the score, the suite fails.

---

## The scoring model

```
overall = Σ (category_score × weight) / Σ (weight of applicable categories)
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

<img src="assets/readme/contribution.png" alt="Category scores against their ceilings" />

Four rules do the heavy lifting:

1. **Missing is not zero.** A category that does not apply leaves the denominator instead of scoring 0 — a fresher is not punished for having no employment history. The report states the applicable weight (here 100 of 100).
2. **Every deduction cites text.** A criterion that fires must attach a verbatim excerpt; a finding without evidence is a bug, and the API refuses to serialise one.
3. **Confidence is a first-class output.** Extraction quality lowers every category's confidence and caps the ATS estimate, so a badly-read document can never present as a clean one.
4. **No model in the number.** The scoring path contains no provider, SDK or network call. A score that changes when a third party is unavailable would not be a score.

---

## Findings: severity is a work queue

<img src="assets/readme/findings.png" alt="Findings by severity" />

13 findings — **2 high, 6 medium, 5 low** — ordered by impact rather than severity, so the first action buys the most points. The top of the real queue:

| Points | Severity | Criterion | Finding | Evidence quoted |
|--:|:--|:--|:--|:--|
| −3.1 | high | CQ-03 | Achievements are described but not measured | *"Worked on latency improvements"* |
| −3.0 | high | SK-04 | Skills claimed but never demonstrated | *"Django, PostgreSQL, Docker, AWS, Kubernetes, Redis"* |
| −1.8 | medium | AT-04 | Date formats are mixed | *"month, year"* |
| −1.7 | medium | SK-05 | Skills not evidenced recently | *"Python"* |
| −1.4 | medium | EX-05 | Claimed skills disconnected from experience | *"aws, django, docker, kubernetes, postgresql"* |
| −1.3 | medium | LR-02 | Verb tense does not match role status | *"Built a ledger service handling 2M daily transactions"* |
| −1.2 | medium | EX-04 | Career progression is not legible | *"Backend Engineer"* |

Each carries an explanation and a remedy. "Unquantified achievement" does not produce a guessed number; it produces a question.

---

## Does the rubric hold? A harness, not a claim

`scripts/calibrate.py` parses eight fixtures with the real parser, scores them with the real engine, and measures whether each candidate weight vector ranks them the way the rubric did.

| Candidate | Spearman ρ | Pairwise accuracy | Tier spread |
|:--|--:|--:|--:|
| **shipped (v1.0.0)** | **0.909** | **0.920** | **39.4** |
| equal-weights | 0.909 | 0.920 | 40.8 |
| ats-heavy | 0.909 | 0.920 | 34.3 |
| content-heavy | 0.873 | 0.880 | 40.7 |
| experience-heavy | 0.873 | 0.880 | 37.7 |

<img src="assets/readme/calibration.png" alt="Calibration: rank agreement per candidate weight vector" />

No alternative beats the shipped vector, so the weights stay — and the claim is now reproducible rather than asserted. **Spearman ρ** asks whether the ranking survives; **pairwise accuracy** asks how often any two fixtures are ordered correctly; **tier spread** asks whether the score actually separates a weak resume from a strong one (it spans **46.4 – 88.3** across the corpus).

This is still **not** an empirical validation: the tiers are rubric-assigned fixtures, not recruiter rankings. That distinction is in `docs/SCORING_METHODOLOGY.md`, in the script's own output, and in [`assets/readme/calibration.json`](assets/readme/calibration.json).

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

On the sample job description — 4 required, 2 preferred — the result is **49.0**:

| Requirement | Status | Meaning in the report |
|:--|:--|:--|
| Python | matched | Listed *and* used in a bullet |
| PostgreSQL | partial | Listed, never demonstrated |
| Kubernetes | partial | Listed, never demonstrated |
| Terraform | absent | Nowhere in the document |
| Kafka *(preferred)* | absent | Nowhere in the document |
| GraphQL *(preferred)* | absent | Nowhere in the document |

The number reads low, and it should: the candidate claims seven technologies and demonstrates one. That is the finding, not a bug — an unevidenced claim is worth less than a visible gap, so the gap advice says *"do not add it unless you have genuinely used it."*

---

## ATS compatibility: an estimate, stated as one

The ATS figure separates **document parseability** from **job keyword relevance** — two different questions that tools routinely merge into one misleading number.

| Check | Result on the sample | Why it matters |
|:--|:--|:--|
| AT-01 Extraction fidelity | pass | If text does not extract, nothing downstream survives |
| AT-02 Reading order | pass | Columns reflow in unpredictable order |
| AT-03 Structural hazards | *not applicable* | The parser reported no layout hazards; assuming none would be a guess |
| AT-04 Date parseability | **warn** | Mixed formats are readable here, fragile elsewhere |
| AT-05 Contact parseability | pass | Email and phone recoverable as text |

3 pass, 1 warn, 1 not applicable → **88.2**. The disclaimer travels with the number in the API payload, the report and the PDF:

> ATS compatibility estimate. Not a prediction of screening outcomes.

Two design decisions are visible in the arithmetic: a document whose extraction confidence falls below 0.5 is **capped at 55** no matter how tidy its formatting looks, and a check that cannot be evaluated leaves the denominator rather than being scored as a failure.

---

## Recommendations that ask instead of invent

13 recommendations from 13 findings: concrete rewrites where the text supports one, questions where it does not.

| Situation | What POTENCIA does | What it will never do |
|:--|:--|:--|
| Bullet has no metric | Asks *"What scale did this work operate at — records, requests per day, users, revenue, or time saved? Give the real figure."* | Insert a plausible number |
| Weak opener ("Responsible for…") | Proposes "Owned …" | Invent scope |
| Skill claimed, never used | Points at the gap and asks which role used it | Add a project |
| Anything factual | Requires your decision in the studio | Auto-replace your resume |

The original parse is **revision 0** and is never overwritten. An edit is a new node pointing at its parent, so history is a tree you can always walk back — and any two versions compare field by field.

---

## Performance, measured

`scripts/profile_engine.py` times the deterministic pipeline with no HTTP, no database and no network. 200 warm runs over eight documents:

| Stage | p50 | p95 | p99 |
|:--|--:|--:|--:|
| Parse | **0.84 ms** | 0.99 ms | 1.10 ms |
| Score (30 criteria) | **0.41 ms** | 0.52 ms | 0.89 ms |
| Parse + score | **1.58 ms** | 2.56 ms | 4.02 ms |
| Job match (12 requirements) | **0.07 ms** | 0.11 ms | 0.20 ms |
| Recommendations | **0.06 ms** | 0.07 ms | 0.09 ms |
| **Full pipeline** | **2.12 ms** | 2.89 ms | 3.49 ms |

Cold start — the first call in a process, paying for imports and regex compilation — is 1.15 ms to parse and 1.01 ms to score.

<img src="assets/readme/scaling.png" alt="Cost per kilobyte and per requirement" />

Cost per kilobyte **falls** as documents grow (1.98 → 1.16 ms/KB across an 8× range), and matching is linear in requirement count (0.038 → 0.014 ms per requirement). Neither curve is a coincidence: the matching engine prepares the resume once per match, and the heading table is ordered once at import.

### What the profile changed

The first profile found two shapes worth fixing, with evidence rather than intuition:

| Fault | Evidence | Fix |
|:--|:--|:--|
| Heading table re-sorted **per line** | ~40% of parse time in one profile | Ordered once at import, bucketed by first word |
| Resume body re-read **per required skill** | A 40-skill match read the document 40 times | One prepared view per match |
| Skill normalisation uncached | `_normalise_key` 4.8 ms per corpus | Bounded `lru_cache` |
| Quadratic duplicate count; verb extracted twice | `list.count` in a loop | `Counter`; leads computed once |

| Stage (same host, same script) | Before | After | Change |
|:--|--:|--:|--:|
| Parse | 2.92 ms | **0.77 ms** | **3.8×** |
| Score | 1.30 ms | **0.37 ms** | 3.5× |
| Job match, 12 requirements | 0.69 ms | **0.06 ms** | 11.5× |
| Job match, 40 requirements | 3.10 ms | **0.40 ms** | 7.8× |
| Full pipeline | 6.17 ms | **1.61 ms** | 3.8× |

Two caveats, because they matter: absolute milliseconds track CPU clock — the same code profiled on an idling laptop at 1.3 GHz reports 2.7 ms for the parse it measures at 0.84 ms boosted — so the **ratio** is the claim, not the microsecond count. And six guardrail tests (`test_performance.py`) now fail if the document is read more than once per match or the heading table is sorted per line, so the regression is caught rather than remembered.

### Request latency

End to end over HTTP against PostgreSQL, 20 runs each, plus one first-analysis call:

| Operation | p50 | Notes |
|:--|--:|:--|
| Upload + parse | 38.2 ms | includes multipart, validation, extraction |
| Analysis — first call | 34.5 ms | pays for connection setup |
| Analysis — steady | **16.7 ms** | p95 20.7 ms |
| Recommendations | 68.8 ms | 13 rules persisted, not just computed |
| Job match | 32.3 ms | 6 requirements |
| PDF report export | 112.1 ms | p95 240.3 ms max — rendering dominates |

<img src="assets/readme/latency.png" alt="Analysis latency across runs" />

These are **request** latencies: authentication, JSON, database and HTTP are inside the number, and they move by tens of percent between runs on a shared machine. The controlled measurement is the engine profile above.

### Under concurrency

`scripts/load_test.py`, 8 clients, 200 analyses, rate limiter disabled so the run measures the engines rather than the throttle:

| Metric | Value |
|:--|--:|
| Analyses completed | **200 / 200** (0 failed) |
| Wall time | 3.31 s |
| Throughput | **60.5 analyses/s** |
| Latency p50 / p95 / p99 | **90.4 / 129.7 / 189.1 ms** |
| Slowest | 207.8 ms |

<img src="assets/readme/load.png" alt="Latency under eight concurrent clients" />

The two numbers describe the same queue: eight clients at a 90 ms median would suggest ~88 asks/s if nothing contended, and the 60.5 measured corresponds to roughly 5.5 requests genuinely in flight — one process, one GIL, one database connection pool. An earlier run of the same script measured 77.4 analyses/s on this machine, so throughput is published as a bound on cost, never as a capacity plan.

---

## Reliability that is enforced, not aspirational

| Concern | Behaviour |
|:--|:--|
| Double submits | `X-Idempotency-Key` replays the original response for 24h; reusing a key on another endpoint is `409` |
| Paging | Keyset cursors on UUIDv7 — rows arriving mid-walk never duplicate or skip |
| Cross-worker limits | Redis-backed counters when `POTENCIA_REDIS_URL` is set; process memory otherwise, logged at startup |
| Downloads | HMAC-signed, account-bound, 15-minute capability URLs |
| Retention | Exports expire in 24h; a scheduled `app.tasks.retention` service deletes files **and** rows |
| Versions | One resume, several named versions; any two compare field by field, any one exports by name |
| Failures | Uniform error envelope with a request id; no stack traces or internal paths reach a client |

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
        SC[Scoring<br/>30 criteria · 6 categories]
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

| Layer | Stack |
|:--|:--|
| Web | React 18 · TypeScript (strict) · Vite 5 · Tailwind · React Router · TanStack Query |
| API | FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · Python 3.12 |
| Data | PostgreSQL 16 · Redis (shared rate-limit counters) |
| Documents | PyMuPDF · python-docx · text-layer extraction with scanned-PDF detection |
| Delivery | Docker · Docker Compose · GitHub Actions · structured JSON logs |

### Repository map

| Path | What lives there |
|:--|:--|
| `backend/app/api/` | routes, dependencies, auth guards, error envelope |
| `backend/app/intelligence/` | parser, scoring, ATS, matching, recommendations — no network calls |
| `backend/app/document/` | validation, extraction, OCR seam, PDF/DOCX rendering |
| `backend/app/services/` | ownership, orchestration, revisions, exports, retention |
| `backend/tests/` | hermetic suite: parser, scoring, ATS, matching, API, security, performance |
| `frontend/src/` | typed API client, dashboard, report, studio, match, export |
| `frontend/e2e/` | Playwright journey against a real stack |
| `scripts/` | every measurement and artefact in this file |
| `assets/readme/` | the figures below, as raw JSON and PNG |
| `docs/` | SRS, architecture, API, scoring, security, testing, status |

---

## Run it

```bash
git clone https://github.com/tdzoro/Potencia && cd Potencia
cp .env.example .env            # set POTENCIA_SECRET_KEY
docker compose up --build       # API on :8000, web on :8080
```

Local development without Docker:

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

Tests that exist to stop the product lying:

- **Score reconciliation** — `sum(findings.score_impact) == 100 - overall` within 0.15.
- **Evidence required** — every finding carries at least one verbatim excerpt.
- **No invented metrics** — a rewrite for an unquantified bullet contains no digits, or asks for the real figure.
- **Partial ≠ absent** — a claimed-but-undemonstrated skill never collapses into a missing one.
- **Original is immutable** — after an edit, revision 0 is byte-identical.
- **Idempotency creates nothing** — a replayed create adds no second row.
- **Efficiency guardrails** — one document read per match; no per-line heading sort.

---

## Limitations

Stated here rather than discovered later:

- **The weights are not empirically validated.** A reproducible harness shows the shipped vector is not beaten by plausible alternatives on eight rubric-ranked fixtures; that is a floor, not a study.
- **The ATS score simulates no specific vendor.** It measures structural parseability, the honest shared denominator.
- **No LLM in the request path.** Recommendations are rules; the provider seam exists and validates any rewrite before use.
- **No OCR engine installed.** Scanned PDFs are detected and reported as `partial` with `ocr_not_performed` rather than silently scored on bad text.
- **No malware scanning** on uploads; no email verification flow.
- **Performance figures are single-host.** One process, one PostgreSQL; the same load script has measured 60.5 and 77.4 analyses/s on this machine at different times, and absolute engine microseconds track CPU clock. No capacity claim is made.
- **Comparison covers summary, skills, experience bullets, projects and education.** Certifications, achievements and leadership lines are carried in every version and exported, but are not diffed field by field.
- **Registration is limited to 5 per 15 minutes per identity**, which a shared office IP can reach.

---

## Documentation

| Document | Contents |
|:--|:--|
| [SRS](docs/SRS.md) | Requirements, journeys, acceptance criteria |
| [Architecture](docs/ARCHITECTURE.md) | Modules, boundaries, sequences, data model |
| [API](docs/API.md) | Every endpoint, payload and error code |
| [Scoring methodology](docs/SCORING_METHODOLOGY.md) | All 30 criteria, weights, applicability, confidence |
| [Security](docs/SECURITY.md) | Controls, threat surface, gaps |
| [Testing](docs/TESTING.md) | Coverage and the assertions that matter |
| [Status](docs/PROJECT_STATUS.md) | Phase-by-phase state and known issues |
| [Audit](docs/REPOSITORY_AUDIT.md) | The original repository assessment and what it drove |

### Reproduce every figure

Nothing above was typed by hand. Each script measures the running product and writes its raw output next to the chart, so a claim and its evidence ship together.

| Script | What it measures | Writes |
|:--|:--|:--|
| `readme_metrics.py` | one real upload → analysis → recommendations → match → exports | `metrics.json`, `latency.png`, `findings.png` |
| `profile_engine.py` | per-stage cost, cold start, size and requirement scaling | `engine_profile.json` |
| `calibrate.py` | five weight vectors against eight rubric-ranked fixtures | `calibration.json` |
| `load_test.py` | 200 analyses across 8 concurrent clients | `load.json` |
| `readme_charts.py` | renders the graphs from the JSON above — measures nothing itself | `calibration.png`, `contribution.png`, `scaling.png`, `load.png` |
| `capture_screenshots.mjs` | the authenticated journey in Chromium, then each screen | `ui-*.png` |
| `report_page.py` | a real generated report PDF, rasterised page one | `report-first-page.png` |

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/profile_engine.py
PYTHONPATH=backend backend/.venv/bin/python scripts/calibrate.py
PYTHONPATH=backend backend/.venv/bin/python scripts/readme_charts.py
```

---

<div align="center">

**POTENCIA** · AI Resume Intelligence

Built by [Arghya Bose](https://github.com/tdzoro) · © 2026 POTENCIA Team · All rights reserved

</div>
