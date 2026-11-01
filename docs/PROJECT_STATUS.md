# Project status

**Last updated:** 1 November 2026
**Current phase:** 20 complete — Google Gemini AI writing assistant integration with prompt-injection and non-fabrication controls
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
150 backend tests, hermetic. Migration round-trip in CI against PostgreSQL 16. **PASS.**

### Phase 15 — Performance
Measured: analysis p50 **14.5 ms**, p95 **16.7 ms**; export p50 **54.5 ms** on a local PostgreSQL container. Concurrent run through `scripts/load_test.py`: 200 analyses across 8 clients in 3.67 s — **54.6 analyses/s**, p50 **99.1 ms**, p95 **197.0 ms**, p99 **228.6 ms**, 0 failures. The same run measured 77.4 analyses/s earlier in the project on this host, so the concurrent figure is not treated as a claim. **PASS** at single-node scale.

### Phase 16 — Deployment
Dockerfiles (non-root API, nginx static web), compose stack with health checks, GitHub Actions running tests, migration round-trip, frontend build, and the browser journey. **PASS.**

### Phase 17 — Contract enforcement
Every claim in `API.md` that had no implementation behind it is now implemented or was never there:

- **Idempotency** (`X-Idempotency-Key`) on all four create endpoints, with 24-hour replay, per-account scoping, `409` for cross-endpoint reuse and `422` for unusable keys. New `idempotency_keys` table and migration.
- **Keyset pagination** on resumes and analyses — `next_cursor` and `has_more` are real, and a malformed cursor is a `422`.
- **Export history** — `GET /analyses/{id}/exports`, surfaced in the UI so a reload no longer forgets generated files.
- **Shared rate limiting** — `LimitStore` seam with an in-memory and a Redis implementation; unreachable Redis degrades loudly, never silently.
- **Weight calibration harness** — eight rubric-ranked fixtures, Spearman and pairwise accuracy per candidate vector. The shipped vector ties for best (`0.909` / `0.920`), so nothing changed; now the claim is reproducible.
- **Browser suite** — eleven Playwright tests over the authenticated journey against a live stack, now part of CI.
- **Named versions** — `resume_revisions.label` with migration `0004`, and `GET /resumes/{id}/revisions/compare` returning a field-level diff between two owned versions. The studio can switch versions, name them and compare them. **PASS.**
- **Scheduled retention** — `app.tasks.retention` removes expired export files and rows; a `retention` service runs it hourly in compose. The 24-hour promise the UI made is now performed by the product.
- **Redis in the stack** — compose ships Redis and the API points `POTENCIA_REDIS_URL` at it, so published limits hold across workers instead of per process.
- **Load harness** — `scripts/load_test.py` drives the analysis endpoint concurrently and stores `assets/readme/load.json`.
- **Crash fixed** — a non-UUID `parent_id` reached `uuid.UUID(...)` in the handler and returned `500`; it is now typed as a UUID and rejected as `422` before the handler runs. Covered by `test_versions.py`.

**PASS.**

### Phase 18 — Version selection and full comparison
**PASS.** The two gaps left open in Phase 17 are closed:

- **Any version can be exported.** `POST /exports` accepts an optional `revision_id` (migration `0005_export_revision`, `exports.revision_id`, `ON DELETE SET NULL`). A version from another resume or account is `404` and queues nothing; `analysis_report` + `revision_id` is `422`. The export screen has a version picker and the history names the version it rendered. Omitting the field preserves the old default — the newest.
- **The diff covers what the studio edits.** `_flatten` now includes projects (name, description, technologies, bullets) and education (institution, degree, field, detail lines) alongside the summary, explicit skills and experience bullets. Those fields are editable in the studio, so the comparison can no longer ignore a change the user actually made.
- **Studio parity.** Projects and education became editable — name, description, technologies, bullets; institution, degree, field, detail lines — and the unsaved-change counter recognises them, so the save button is not disabled while a project edit is pending.

**PASS.**

### Phase 19 — Proprietary licence and engine efficiency

**Licence.** The MIT text was replaced by an all-rights-reserved proprietary licence held by the POTENCIA Team, at the holder's instruction; the README badge, footer and npm manifest were updated with it, and `TD-6` in the repository audit is marked resolved. GitHub will re-detect the licence on the next push.

**Efficiency, measured before it was changed.** `scripts/profile_engine.py` times each deterministic stage and sweeps document size and requirement count, so a change is justified by a number rather than an adjective. It found two quadratic-ish shapes:

| Fault | Evidence | Fix |
|:--|:--|:--|
| Heading keyword table re-sorted per line | ~40% of parse time in a single profile | Ordered once at import, and bucketed by first word so a line tests a handful of candidates, not ninety |
| Resume body re-read per required skill | 40-skill match read the document 40 times | One `_ResumeView` per match: canonical sets, prose and per-role haystacks prepared once |
| Skill normalisation uncached | 4.8 ms per corpus in `_normalise_key` | Bounded `lru_cache`, and one normalisation per match instead of two |
| Quadratic duplicate-skill count, repeated verb extraction | `list.count` in a loop; `lead_verb` called twice per bullet | `Counter`; the lead verbs are computed once and zipped |

Result, same host and same script: parse **2.92 → 0.77 ms**, score **1.30 → 0.37 ms**, job match **0.69 → 0.06 ms** (11.5×), full pipeline **6.17 → 1.61 ms** (3.8×), 40-requirement match **3.10 → 0.40 ms**. Parsing is now flat per kilobyte across an 8× size range.

Six guardrail tests make the regression catchable rather than remembering it: heading ordering, a classification budget, one document read per match, a 40-requirement budget, an eight-document parse budget, and a cache-hit assertion. Scores are unchanged — the suite and the calibration harness produce the same numbers.

**PASS.**

### Phase 20 — Gemini AI rewrite provider

**Provider implementation.** Implemented `GeminiRewriteProvider` implementing `RewriteProvider` (`app/ai/providers/gemini.py`) using the official Google Gen AI Python SDK (`google-genai`). Dynamically selected via `GEMINI_API_KEY` and `GEMINI_MODEL` (`gemini-2.5-flash` default). When unconfigured, `NullRewriteProvider` ensures transparent deterministic fallback without breaking any workflow.

**Strict anti-hallucination & non-fabrication.** The model acts solely as an editorial rewrite assistant:
- Never invents employers, dates, qualifications, certifications, or technical skills.
- Never invents numerical metrics, percentages, dollar amounts, or operational scale.
- Where a metric would strengthen a bullet, the model populates `requires_user_input` asking the user for the real figure instead of fabricating one.
- An automated post-validation gate detects and rejects proposals that introduce new numerical digits when the original text had none.

**Prompt injection defense.** Untrusted resume content is isolated within `<untrusted_resume_content>` delimiters with escaping. System instructions explicitly forbid the model from executing or acknowledging embedded directives. Strict Pydantic output schemas enforce structured JSON.

**Zero scoring impact.** The deterministic parsing, ATS, and scoring engines remain 100% untouched. Gemini output affects only advisory recommendation text and is labelled `source: "gemini"`.

**Resilience & caching.** 30-second timeouts, graceful degradation on 429 rate limits or timeouts, and bounded in-memory LRU caching to eliminate duplicate API calls. Regeneration endpoint `POST /api/v1/recommendations/{id}/regenerate` allows on-demand fresh rewrites with cache bypassing.

**Frontend.** Recommendations page includes an AI rewrite indicator, side-by-side comparison, manual edit modal, regenerate action with loading state, and error handling.

**Hermetic test suite.** 15 unit and integration tests added in `backend/tests/test_gemini_provider.py` mocking the Gen AI SDK. All 165 backend tests pass hermetically without a real API key.

**PASS.**

---

## Verified end to end

Register → upload → parse → analyse → recommendations (deterministic + Gemini AI rewrite) → decide → revise → export (PDF + DOCX) → match, over HTTP against PostgreSQL / SQLite, with downloaded documents re-opened and searched for their real contents.

Browser journey verified in Chrome: score rendered from the DOM, acceptance persisted across reload, signed download link present, a job description producing a named gap, a revision saved without altering the original.

---

## Known issues

| ID | Issue | Severity | Notes |
|:--|:--|:--|:--|
| KI-1 | Weights not empirically validated | Medium | Harness shows the shipped vector is not beaten by alternatives on rubric fixtures; that is a floor, not a study |
| KI-2 | No LLM provider | Resolved | Optional Google Gemini provider implemented behind the provider seam in Phase 20 |
| KI-4 | No malware scanning on uploads | Medium | Type and size checked only |
| KI-5 | No email verification flow | Low | Field stored, no mail sent |
| KI-6 | OCR engine not installed | Low | Scanned documents are detected and labelled `ocr_not_performed`, never silently scored |
**Resolved in Phase 17:** per-process-only rate limits, missing export history, absent browser automation, unverified click-through of the match view, manual-only retention (now scheduled in compose), multi-version resumes (now labelled with comparison), a `500` on a malformed `parent_id`, and export rows mislabelled with an expiry as a generation time.

---

## Technical debt

- `POST /auth/login` is rate limited per identity; a shared office IP can still exhaust the registration budget.
- Jobs and matches are stored; the UI lists jobs but not past matches for a resume.
- No cursor support in the web client yet — lists fetch the first page only.
- The comparison view diffs summary, explicit skills, experience bullets, projects and education. Certifications, achievements and leadership lines are carried in every snapshot and exported, but are not diffed field by field.

---

## Next

1. Calibration study with independently ranked resumes, then a `methodology_version` bump if the weights move.
2. Multi-process load test and a second host, so throughput can be quoted beyond one process.
