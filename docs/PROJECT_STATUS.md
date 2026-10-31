# Project status

**Last updated:** 1 November 2026
**Current phase:** 17 complete — contracts enforced, journey proven in a browser
**Methodology version:** 1.0.0

---

## Phase completion report

### Phase 0 — Repository audit
**PASS.** Audit in `docs/REPOSITORY_AUDIT.md`; drove the build order rather than a migration.

### Phase 1 — Specification and design
**PASS.** `SRS.md`, `ARCHITECTURE.md`, `API.md`, `SCORING_METHODOLOGY.md`.

### Phase 2 — Foundation
FastAPI factory, settings with production guards, SQLAlchemy, Alembic, structured JSON logging with request ids, error envelope, CORS allow-list, React + Vite + Tailwind, health endpoint. **PASS.**

### Phase 3 — Database and authentication
8 tables, UUIDv7 keys, bcrypt, access/refresh JWTs, `token_version` revocation, registration/login/refresh/logout/me/delete, isolation returning `404`. **PASS.**

### Phase 4 — Document ingestion
PDF and DOCX extraction, magic-byte and streaming size validation, scanned-document detection with confidence, page counts, honest failure. **PASS.**

### Phase 5 — Resume intelligence
Section segmentation, entity extraction, date normalisation, skill taxonomy, explicit vs inferred skills, uncertainty recorded rather than guessed. **PASS.**

### Phase 6 — Scoring engine
27 criteria across 6 weighted categories, applicability handling, per-criterion confidence, evidence on every finding, deterministic arithmetic, methodology versioning. **PASS.**

### Phase 7 — ATS engine
Structural checks with evidence and remediation; estimate separated from keyword relevance; disclaimer in the payload. **PASS.**

### Phase 8 — Job matching
Requirement extraction with section bucketing, canonicalisation, four skill states, demonstrated-years arithmetic, education ranking, deterministic weighting. **PASS.**

### Phase 9 — Recommendations
Deterministic rules from findings: rewrites where the text supports one, questions where it does not. Provider seam with schema validation and a null implementation; no model in the request path. **PASS.**

### Phase 10 — Improvement studio
Revision tree with revision 0 immutable, parent linkage, full-structure snapshots, per-recommendation decisions. **PASS.**

### Phase 11 — Frontend
14 routes, all wired to live endpoints; loading, error and empty states; strict typecheck and production build green; every route rendered in a headless browser with a seeded session. **PASS.**

### Phase 12 — Export
PDF report, PDF and DOCX resume, signed 15-minute URLs, files re-opened by a parser after rendering, newest approved revision exported, export history endpoint and UI. **PASS.**

### Phase 13 — Security hardening
Rate limiting through a pluggable store (memory or Redis), security headers, signed downloads, streaming upload caps, ownership checks, secret management, retention sweep. **PASS**, with `KI-4` and `KI-5` open.

### Phase 14 — QA
140 backend tests, hermetic. Migration round-trip in CI against PostgreSQL 16. **PASS.**

### Phase 15 — Performance
Measured: analysis p50 **22.1 ms**, p95 **26.3 ms**; export p50 **87.2 ms** on a local PostgreSQL container. Concurrent run through `scripts/load_test.py`: 200 analyses across 8 clients in 2.59 s — **77.4 analyses/s**, p50 **72.3 ms**, p95 **142.8 ms**, p99 **155.8 ms**, 0 failures. **PASS** at single-node scale.

### Phase 16 — Deployment
Dockerfiles (non-root API, nginx static web), compose stack with health checks, GitHub Actions running tests, migration round-trip, frontend build, and the browser journey. **PASS.**

### Phase 17 — Contract enforcement
Every claim in `API.md` that had no implementation behind it is now implemented or was never there:

- **Idempotency** (`X-Idempotency-Key`) on all four create endpoints, with 24-hour replay, per-account scoping, `409` for cross-endpoint reuse and `422` for unusable keys. New `idempotency_keys` table and migration.
- **Keyset pagination** on resumes and analyses — `next_cursor` and `has_more` are real, and a malformed cursor is a `422`.
- **Export history** — `GET /analyses/{id}/exports`, surfaced in the UI so a reload no longer forgets generated files.
- **Shared rate limiting** — `LimitStore` seam with an in-memory and a Redis implementation; unreachable Redis degrades loudly, never silently.
- **Weight calibration harness** — eight rubric-ranked fixtures, Spearman and pairwise accuracy per candidate vector. The shipped vector ties for best (`0.909` / `0.920`), so nothing changed; now the claim is reproducible.
- **Browser suite** — nine Playwright tests over the authenticated journey against a live stack, now part of CI.
- **Named versions** — `resume_revisions.label` with migration `0004`, and `GET /resumes/{id}/revisions/compare` returning a field-level diff between two owned versions. The studio can switch versions, name them and compare them. **PASS.**
- **Scheduled retention** — `app.tasks.retention` removes expired export files and rows; a `retention` service runs it hourly in compose. The 24-hour promise the UI made is now performed by the product.
- **Redis in the stack** — compose ships Redis and the API points `POTENCIA_REDIS_URL` at it, so published limits hold across workers instead of per process.
- **Load harness** — `scripts/load_test.py` drives the analysis endpoint concurrently and stores `assets/readme/load.json`.
- **Crash fixed** — a non-UUID `parent_id` reached `uuid.UUID(...)` in the handler and returned `500`; it is now typed as a UUID and rejected as `422` before the handler runs. Covered by `test_versions.py`.

**PASS.**

---

## Verified end to end

Register → upload → parse → analyse → recommendations → decide → revise → export (PDF + DOCX) → match, over HTTP against PostgreSQL, with downloaded documents re-opened and searched for their real contents.

Browser journey verified in Chrome: score rendered from the DOM, acceptance persisted across reload, signed download link present, a job description producing a named gap, a revision saved without altering the original.

---

## Known issues

| ID | Issue | Severity | Notes |
|:--|:--|:--|:--|
| KI-1 | Weights not empirically validated | Medium | Harness shows the shipped vector is not beaten by alternatives on rubric fixtures; that is a floor, not a study |
| KI-2 | No LLM provider | Low | Deliberate; seam exists and validates any rewrite |
| KI-4 | No malware scanning on uploads | Medium | Type and size checked only |
| KI-5 | No email verification flow | Low | Field stored, no mail sent |
| KI-6 | OCR engine not installed | Low | Scanned documents are detected and labelled `ocr_not_performed`, never silently scored |
**Resolved in Phase 17:** per-process-only rate limits, missing export history, absent browser automation, unverified click-through of the match view, manual-only retention (now scheduled in compose), multi-version resumes (now labelled with comparison), a `500` on a malformed `parent_id`, and export rows mislabelled with an expiry as a generation time.

---

## Technical debt

- `POST /auth/login` is rate limited per identity; a shared office IP can still exhaust the registration budget.
- Jobs and matches are stored; the UI lists jobs but not past matches for a resume.
- No cursor support in the web client yet — lists fetch the first page only.
- The comparison view diffs summary, explicit skills and experience bullets. Projects and education are editable in the structure but not yet compared.
- Exports always render the newest revision; choosing a named version to export is not yet offered.

---

## Next

1. Calibration study with independently ranked resumes, then a `methodology_version` bump if the weights move.
2. Export a chosen named version instead of always the newest, and compare projects and education as well.
3. Optional LLM rewrite provider behind the existing seam, with prompt-injection controls documented before it ships.
4. Multi-process load test and a second host, so throughput can be quoted beyond one process.
