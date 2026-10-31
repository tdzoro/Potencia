# POTENCIA — Project Status

**Last updated:** 2026-11-01
**Current phase:** 2 — Foundation & Infrastructure · **COMPLETE**
**Next phase:** 3 — Database & Authentication
**Methodology version:** `1.0.0` (specified; implemented in Phase 6)

This file is updated at the end of every phase. It records what is true, including what is not working.

---

## Phase tracker

| Phase | Objective | Exit criteria | Status |
|:-:|:--|:-:|:-:|
| 0 | Repository audit & implementation plan | PASS | ✅ Complete |
| 1 | Product specification & system design | PASS | ✅ Complete |
| 2 | Foundation & infrastructure | PASS | ✅ Complete |
| 3 | Database & authentication | — | ○ Not started |
| 4 | Document ingestion & parsing | — | ○ Not started |
| 5 | Resume intelligence engine | — | ○ Not started |
| 6 | Explainable scoring engine | — | ○ Not started |
| 7 | ATS compatibility engine | — | ○ Not started |
| 8 | Job description matching | — | ○ Not started |
| 9 | AI recommendation engine | — | ○ Not started |
| 10 | Resume improvement studio | — | ○ Not started |
| 11 | Frontend product experience | — | ○ Not started |
| 12 | PDF & DOCX export | — | ○ Not started |
| 13 | Security & privacy hardening | — | ○ Not started |
| 14 | Testing & QA | — | ○ Not started |
| 15 | Performance & reliability | — | ○ Not started |
| 16 | Production deployment | — | ○ Not started |

---

## Phase 1 — Completion report

**Objective:** establish exactly what is being built, in contracts precise enough to implement against.

### Implemented

1. `docs/SRS.md` — vision, four personas, four user journeys, 96 numbered functional requirements across modules A–J with testable acceptance criteria, 19 non-functional requirements with measurable targets, data/privacy requirements, constraints, assumptions, explicit non-claims, out-of-scope, traceability matrix.
2. `docs/ARCHITECTURE.md` — architectural drivers, system context, per-layer component boundaries with allowed imports, four request-lifecycle sequence diagrams, entity-relationship outline, storage strategy, AI provider abstraction, failure/degradation matrix, observability, topology, eight ADRs.
3. `docs/API.md` — conventions (versioning, auth, pagination, idempotency, async resources), eleven data objects, all `/api/v1` endpoints with request and response shapes, rate limits, per-endpoint obligations.
4. `docs/SCORING_METHODOLOGY.md` — normative scoring rules: six weighted categories, 27 criteria with explicit measurement formulas, applicability rules, double-penalty ownership map, confidence derivation, versioning, calibration plan, worked example.

### Design decisions worth recording

- **Deterministic-first is enforced structurally, not culturally.** The numeric score is computed before any provider call; an LLM finding carries `score_impact: null` and cannot move a number. Stated in the SRS as FR-D-01/FR-D-02 and tested in Phase 6.
- **`job_match` is never blended into `overall`.** A resume is not worse for targeting a different role.
- **Not-applicable is excluded, not zeroed.** A first-time candidate loses the experience weight from the denominator rather than scoring 0 for work they have not done.
- **Task queue deferred.** ADR-06 keeps Phase 4 on an in-process runner; Redis arrives only when background work actually exists.

### Contract defects found and fixed during this phase

| Defect | Resolution |
|:--|:--|
| `API.md` §3.4 claimed the overall denominator renormalises when a job description is absent, but the methodology weights the six intrinsic categories to exactly 100 with no job-match component | Corrected §3.4: `overall` is identical with or without a job description |
| `API.md` §1.4 required the error envelope on *every* non-2xx, while §3.1 put health fields at the top level of the `503` | Documented an explicit single exception for `GET /health` as a probe, keeping both requirements satisfiable |
| Stray label `"jurisdiction"` in the `Scores` object | Replaced with the intended applicability rule |

---

## Phase 2 — Completion report

**Objective:** a stable engineering foundation that starts, communicates, and fails observably.

### Implemented

1. **Backend** (24 files) — FastAPI app factory, environment-driven settings (`POTENCIA_*`, pydantic-settings), JSON structured logging with request-id `ContextVar`, global exception handlers emitting the documented envelope, CORS allow-list, SQLAlchemy 2.x engine with lazy construction and `pool_pre_ping`, Alembic scaffold reading the configured URL, `/health` with dependency status, pytest suite.
2. **Frontend** (30 files) — React 18 + TypeScript + Vite + Tailwind, `createBrowserRouter` with `/`, `/status`, `*`, typed API service layer with abort-based timeouts and `ApiError` carrying `code`/`requestId`, TanStack Query health hook, error boundary, accessible responsive layout, brand identity, landing / live system-status / 404 pages.
3. **Infrastructure** — `docker-compose.yml` (Postgres 16 + API + web, health-gated startup), backend and frontend Dockerfiles (non-root, multi-stage), `.gitignore`, `.env.example` for both applications.
4. **Brand** — monogram cropped from the supplied lockup as a standalone `/mark.png` for the header; the full lockup used in the hero and README.

### Tests executed

| Check | Command | Result |
|:--|:--|:-:|
| Backend unit tests | `pytest -q` (6 tests) | **6 passed** |
| Backend install | `pip install -r requirements.txt` in `backend/.venv` | OK |
| SPA served | `GET :5173/` | **200**, correct `<title>` |
| SPA deep route | `GET :5173/status` | **200** (history fallback) |
| Proxy → API | `GET :5173/health` | **200**, live backend JSON |
| Proxy → API error | `GET :5173/api/v1/missing` | **404**, documented envelope |
| Frontend types | `npm run typecheck` | **Pass** |
| Frontend build | `npm run build` | **Pass** — 263 kB JS (84.5 kB gzip) |

### Live verification (real HTTP, real PostgreSQL)

| Scenario | Expected | Observed |
|:--|:--|:--|
| `/health` with database reachable | `200`, `status: ok`, `dependencies.database: ok` | ✅ |
| Database stopped | `503`, `status: degraded`, `dependency_unavailable` | ✅ |
| Database restarted | Recovers to `200` **without restarting the API** | ✅ |
| Unknown route | `404` with `not_found` envelope | ✅ |
| Wrong method | `405` with `method_not_allowed` | ✅ (was `validation_error` — fixed) |
| Allowed origin | `Access-Control-Allow-Origin: http://localhost:5173` | ✅ |
| Foreign origin | No allow-origin header | ✅ |
| Request id | Generated when absent, echoed when well-formed | ✅ |
| Injected request id (`<script>`) | Replaced with a generated id | ✅ |
| Log shape | JSON, `request_id` propagated into access logs, no bodies | ✅ |

### Files created

`backend/` — 24 files · `frontend/` — 30 files · `docs/` — 4 files · root — 3 files (`docker-compose.yml`, `.gitignore`, `.env.example`)

### Known issues

| ID | Issue | Severity | Disposition |
|:--|:--|:-:|:--|
| KI-4 | Port 8000 is occupied on the development host by an unrelated process, so verification ran on 8020 and the dev proxy target was made overridable (`POTENCIA_API_TARGET`) | Low | Environment-specific; documented, not worked around in code |
| KI-5 | Starlette `TestClient` emits a deprecation warning recommending `httpx2` | Info | Non-fatal; revisit when the test client moves |
| KI-6 | Frontend is not yet covered by automated component tests | Medium | Phase 11/14 — the foundation has no interactive logic to test yet |
| KI-1 | Licence holder reads `MIM` while the repository owner is `tdzoro` | Medium | Owner decision, unchanged |
| KI-3 | ~~No `.gitignore`~~ | — | **Resolved** in Phase 2 |

### Security concerns

- Credentials are environment-only; `alembic.ini` carries no URL, so no credential is committed. Production refuses to start while `secret_key` holds the development placeholder.
- CORS is an explicit allow-list; a wildcard with credentials is impossible.
- Upload validation, prompt-injection defence and rate limiting are specified (Phases 4, 9, 13) but **not implemented** — there is no upload path yet.
- `/health` reports dependency state without exposing connection strings or versions.

### Performance concerns

Nothing measurable yet. Baseline recorded: backend startup ~1 s, SPA bundle 263 kB (84.5 kB gzip), `/health` round-trip < 5 ms locally.

### Technical debt

| ID | Debt | Phase |
|:--|:--|:-:|
| TD-9 | `api_router` is mounted but empty — no `/api/v1` routes exist yet | 3 |
| TD-10 | No CI workflow, so the passing checks above are manual | 2 follow-up / 16 |
| TD-11 | `target_metadata = None` in Alembic until models exist | 3 |
| TD-12 | Frontend has no test runner configured | 11 |
| TD-13 | `frontend/Dockerfile` bakes the API URL at build time; a runtime-configurable build is preferable before multi-environment deploys | 16 |

### Documentation updated

`README.md` (status, local development, documentation index) · `docs/PROJECT_STATUS.md` (this file) · `docs/API.md` (three contract corrections)

### Exit criteria

Both applications run; the frontend reaches the backend; the database connection is real and its failure is observable; no secret is trackable. **PASS.**

---

## Blockers

| ID | Blocker | Impact | Resolution |
|:--|:--|:--|:--|
| B-1 | `admin: false` on the repository | Cannot create Actions secrets, branch protection or deployment environments | Owner action, required by Phase 16 |
| B-2 | Licence holder mismatch (KI-1) | Public attribution ambiguity | Owner decision before launch |

No blocker prevents Phase 3.

---

## Immediate next actions

1. **Phase 3:** domain models (User, Resume, ResumeRevision, Analysis, Job, Match, Recommendation, Export), Alembic initial migration, registration/login/refresh, per-user query scoping.
2. Prove isolation with a test that a second user receives `404` — not `403` — for another user's resource.
3. Add the CI workflow so the checks in this report stop being manual.
