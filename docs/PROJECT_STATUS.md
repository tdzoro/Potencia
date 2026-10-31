# Project status

**Last updated:** 1 November 2026
**Current phase:** 16 complete — implementation finished, calibration pending
**Methodology version:** 1.0.0

---

## Phase completion report

### Phase 0 — Repository audit
**Exit criteria:** PASS. Audit in `docs/REPOSITORY_AUDIT.md`; the repository was a specification-first skeleton, so the audit drove the build order rather than a migration.

### Phase 1 — Specification and design
**Exit criteria:** PASS. `SRS.md`, `ARCHITECTURE.md`, `API.md`, `SCORING_METHODOLOGY.md`.

### Phase 2 — Foundation
FastAPI factory, settings with production guards, SQLAlchemy, Alembic, structured JSON logging with request ids, error envelope, CORS allow-list, React + Vite + Tailwind, health endpoint. **PASS.**

### Phase 3 — Database and authentication
8 tables, UUIDv7 primary keys, bcrypt, access/refresh JWTs, `token_version` revocation, registration/login/refresh/logout/me/delete, user isolation returning `404`. **PASS.**

### Phase 4 — Document ingestion
PDF (PyMuPDF) and DOCX extraction, magic-byte and size validation enforced while streaming, scanned-document detection with confidence, page counts, honest failure. **PASS.**

### Phase 5 — Resume intelligence
Section segmentation, contact/education/experience/project/certification extraction, date normalisation, skill taxonomy with canonical names and aliases, explicit vs inferred skills kept separate, uncertainty recorded rather than guessed. **PASS.**

### Phase 6 — Scoring engine
27 criteria across 6 weighted categories, applicability handling (missing ≠ zero), per-criterion confidence, evidence on every finding, deterministic arithmetic, methodology versioning. Score/impact reconciliation is a test. **PASS.**

### Phase 7 — ATS engine
Structural checks with pass/warn/fail, evidence and remediation; estimate separated from keyword relevance; disclaimer carried in the payload. **PASS.**

### Phase 8 — Job matching
Requirement extraction with section bucketing, canonicalisation, three-state skill matching (`matched` / `partial` / `weakly_demonstrated` / `absent`), demonstrated-years arithmetic with overlap trimming, education rank comparison, responsibility overlap, deterministic weighting. **PASS.**

### Phase 9 — Recommendations
Deterministic rule generation from findings: concrete rewrites where the text supports one, questions where it does not. Provider seam (`app/ai/providers`) with schema validation and a null implementation. No model in the request path. **PASS.**

### Phase 10 — Improvement studio
Revision tree with revision 0 immutable, parent linkage, full-structure snapshots, accept/reject/edit decisions persisted per recommendation. **PASS.**

### Phase 11 — Frontend
14 routes: landing, status, login, register, dashboard, upload, history, settings, report, recommendations, match, export, improvement studio, 404. All wired to live endpoints; loading, error and empty states throughout; strict typecheck and production build green. **PASS.**

### Phase 12 — Export
PDF analysis report, PDF and DOCX improved resume, signed 15-minute download URLs, files re-opened by a parser after rendering, newest approved revision exported. **PASS.**

### Phase 13 — Security hardening
Rate limiting, security headers, signed downloads, streaming upload caps, ownership checks, secret management, retention sweep. See `SECURITY.md` for what is deliberately not done. **PASS**, with `KI-9` and `KI-10` recorded below.

### Phase 14 — QA
108 tests, hermetic (no database, no network). Migration round-trip in CI against PostgreSQL 16. **PASS.**

### Phase 15 — Performance
Measured, not assumed: analysis p50 **22.1 ms**, p95 **26.3 ms**; export p50 **87.2 ms** on a local PostgreSQL container. **PASS** at single-user scale; no load test exists.

### Phase 16 — Deployment
Dockerfiles (non-root API, nginx static web), compose stack with health checks, GitHub Actions running tests, migration round-trip and the frontend build. **PASS.**

---

## Verified end to end

Register → upload → parse → analyse → recommendations → decide → revise → export (PDF + DOCX) → match, executed against PostgreSQL over HTTP, with downloaded documents re-opened and searched for their real contents.

Sample result: **82.6 / 100** (strong), ATS **88.2**, 13 findings, 5 priority actions, 13 recommendations, job match **49.0** with three skills matched or partial and two absent.

---

## Known issues

| ID | Issue | Severity | Notes |
|:--|:--|:--|:--|
| KI-1 | Scoring weights uncalibrated | Medium | Product-design hypotheses, versioned and disclosed in every report |
| KI-2 | No LLM provider | Low | Deliberate: rules only, so nothing can be fabricated; seam exists |
| KI-3 | Rate limits are per process | Medium | Needs Redis before multi-worker deployment |
| KI-4 | No malware scanning on uploads | Medium | Type and size checked only |
| KI-5 | No email verification flow | Low | Field stored, no mail sent |
| KI-6 | OCR fallback path not exercised against a real scanned PDF | Low | Detection and confidence are tested; the OCR engine is not installed |
| KI-7 | Exports list is not persisted in the UI | Low | API returns records; the page keeps them in session state |
| KI-8 | No browser automation suite | Low | Frontend verified by typecheck, build and headless render of each route |
| KI-9 | Match result table not clicked through headlessly | Low | Payload and rendering path verified separately |
| KI-10 | Retention sweep is manual | Low | `python -m app.tasks.retention` needs a scheduler |

---

## Technical debt

- API.md documents `X-Idempotency-Key` on create endpoints; it is not enforced. Replays are prevented by unique constraints where they matter, not by a replay cache.
- `GET /analyses?cursor=` and `GET /resumes?cursor=` accept a limit but do not implement cursor pagination.
- Job descriptions and matches are stored; the UI lists jobs but not past matches.
- `/exports` has no list endpoint, so a page reload forgets prior exports.

---

## Next

1. Calibration study for the six weights, then bump `methodology_version`.
2. Redis-backed rate limiting and a queue for OCR-heavy documents.
3. Optional LLM rewrite provider behind the existing seam, with prompt-injection controls documented in `ARCHITECTURE.md`.
4. Multi-version resumes and per-role comparison.
