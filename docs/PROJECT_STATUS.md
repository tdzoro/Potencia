# Project status

**Last updated:** 1 November 2026
**Current phase:** 24 complete — Comprehensive Testing, Quality Assurance & Performance Audit
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

### Phase 24 — Comprehensive Testing, Quality Assurance & Performance Audit
**PASS.**
- **Complete Codebase Audit:** Identified and classified 11 architectural, security, and performance findings (C-1, C-2, H-1 to H-4, M-1 to M-3, L-1, L-2). All resolved.
- **Critical Frontend Runtime Crash Bug Fixes:** Fixed unhandled exceptions in `RecommendationsPage.tsx` (nullish check on `requires_user_input`) and `StudioPage.tsx` (nullish checks on `copy.projects`, `copy.education`, and `skills.inferred`).
- **Alembic Migration SQLite Batch Compatibility:** Updated `0005_export_revision.py` and `env.py` with `render_as_batch=True`. Created programmatic migration round-trip test (`upgrade head` $\to$ `downgrade -1` $\to$ `upgrade head`) in `backend/tests/test_migrations.py`.
- **Multi-Tenant Row-Level Isolation:** Implemented comprehensive cross-tenant isolation test suite (`backend/tests/test_tenant_isolation.py`) ensuring strict `404 Not Found` returns across resumes, revisions, analyses, recommendations, jobs, matches, and exports.
- **ATS Engine Extreme Boundary Tests:** Implemented `backend/tests/test_ats_boundaries.py` validating score bounds ($[0, 100]$), score reconciliation identities (`overall_score + sum(findings.score_impact) == 100`), empty resumes, single-word resumes, 12,000-word documents, and degenerate job matching.
- **Concurrent AI Pre-Fetching Performance:** Upgraded recommendation generation in `recommendation_service.py` to pre-fetch top candidates using a bounded `ThreadPoolExecutor`, reducing cold request latency by up to 5x with instant fallback to deterministic rules.
- **Deterministic Engine Performance Profiling:** Executed `scripts/profile_engine.py`: warm parse p50 **0.82 ms**, warm score p50 **0.47 ms**, full pipeline p50 **1.70 ms** (p95 **2.31 ms**), sub-linear scaling up to 8x size (1.11 ms/KB). Saved to `assets/readme/engine_profile.json`.
- **Frontend Unit & Component Testing:** Configured Vitest 2.1.9 and React Testing Library (`frontend/package.json`, `frontend/vite.config.ts`). Created 19 automated tests covering Authentication, Upload, Studio, Recommendations, and Export.
- **Playwright E2E Suite Expansion:** Expanded `frontend/e2e/journey.spec.ts` covering all 14 end-to-end user journeys (registration, email verification, login, upload, text extraction, OCR fallback, job match, ATS scoring, AI rewrites, accept/reject, revisions history, exports download, password recovery, logout).
- **Backend Test Suite Total:** 234 passing tests, 1 conditional skipped test, 0 failures across 26 test files.

**PASS.**

---

- **One-time Cryptographic Tokens:** Generated using `secrets.token_urlsafe(32)` with high entropy.
- **Hashed Database Storage:** Stored strictly as SHA-256 digests in `auth_tokens` table with expiration (`expires_at`) and single-use enforcement (`used_at`). Raw tokens are never persisted to disk or database. Alembic migration `0006_auth_tokens.py`.
- **Complete Email Verification Flow:** Verification tokens dispatched automatically on registration; validated via `POST /api/v1/auth/verify-email`, resendable via `POST /api/v1/auth/resend-verification`. Configurable enforcement (`POTENCIA_EMAIL_VERIFICATION_REQUIRED`) on sign-in and protected endpoints.
- **Secure Password Recovery:** `POST /api/v1/auth/forgot-password` and `POST /api/v1/auth/reset-password`. Enforces 12-character minimum passwords, hashes with bcrypt, consumes tokens once, and increments `user.token_version`, immediately revoking all existing active refresh tokens across devices.
- **Anti-Account Enumeration:** Generic 200 responses and constant-time dummy comparisons returned on forgot-password and resend-verification to prevent discovering registered user emails.
- **Modular Email Service:** `backend/app/services/email_service.py` provides production SMTP delivery over TLS/SSL and an in-memory queue (`_SENT_EMAILS`) for hermetic testing. Features responsive HTML and plain text templates for verification, reset, password change notification, and welcome.
- **Rate Limiting:** Added strict rate limit rules to `backend/app/core/ratelimit.py` (5-10 requests per 15 minutes) on all verification and recovery endpoints.
- **Frontend Integration:** Added `VerifyEmailPage.tsx`, `ForgotPasswordPage.tsx`, and `ResetPasswordPage.tsx`, updated `RegisterPage.tsx`, `LoginPage.tsx`, and `App.tsx` with resend actions and unverified account notices.
- **Comprehensive Test Suite:** 18 automated tests in `backend/tests/test_verification_and_recovery.py`. Entire test suite of 227 backend tests passes hermetically.

**PASS.**

---

### Phase 22 — Optical Character Recognition (OCR) for Scanned Resumes
**PASS.**
- **Modular OCR engine:** Created `backend/app/document/ocr.py` and `backend/app/services/ocr_service.py` integrating Tesseract OCR via `pytesseract` and PyMuPDF page rasterization.
- **OpenCV image preprocessing:** Implemented `preprocess_image` with grayscale conversion, CLAHE adaptive contrast enhancement, Gaussian noise filtering, Otsu binarization, and safe contour-based deskewing (`deskew_image`).
- **Intelligent automatic extraction:** Updated `backend/app/document/extraction.py` to inspect PDF text density; ordinary text-based PDFs bypass OCR for zero overhead, while scanned and image-dominant PDFs automatically trigger OCR.
- **Confidence & quality tracking:** Computes word-level and page-level confidences, records low-confidence warnings (`ocr_low_confidence`), detects unreadable scans, and flags missing Tesseract installations (`ocr_engine_missing`) gracefully without server crashes.
- **Frontend enhancement:** Updated `frontend/src/pages/UploadPage.tsx` with scanned PDF support badges, real-time OCR extraction indicators, dedicated OCR quality warning cards with actionable scanning guidance, and unreadable document states.
- **Docker & environment configuration:** Updated `backend/Dockerfile` with `tesseract-ocr`, `tesseract-ocr-eng`, `libgl1`, and `libglib2.0-0`. Added `POTENCIA_OCR_*` settings to `config.py`, `.env.example`, and `docker-compose.yml`.
- **Automated test suite:** 14 unit and integration tests added in `backend/tests/test_ocr.py`. Total backend test suite now 209 tests, all passing hermetically.

**PASS.**

---

### Phase 21 — Security Hardening & Secure Document Processing
**PASS.**
- **Malware scanning integration:** Implemented native pure-Python ClamAV `INSTREAM` streaming protocol client over TCP (`backend/app/services/malware_scanner.py`) with configurable socket timeouts and zero third-party dependencies.
- **Fail-safe production controls:** Outages and timeouts fail closed (`503 Service Unavailable`) when running in production (`POTENCIA_ENVIRONMENT=production` or `POTENCIA_CLAMAV_REQUIRED=true`), preventing unscanned files from entering storage. In development/testing, falls back gracefully to test scanning.
- **EICAR signature detection:** Built-in detection of the standard EICAR test signature rejecting malicious files with `422 Unprocessable Entity` containing the threat classification.
- **Filename sanitization:** `sanitize_filename` strips Unix/Windows directory traversal (`../`, `..\`), null bytes, control characters, and reserved Windows device names (`CON`, `PRN`, `NUL`), enforcing a 255-character maximum with safe fallback.
- **PDF security:** Rejection of encrypted/password-protected PDFs (`needs_pass`), page count limits (`POTENCIA_MAX_PDF_PAGES=50`), corrupted PDF handling, and embedded executable/script attachment inspection.
- **DOCX container security:** Rejection of ZIP bombs and unsafe compression ratios (> 100:1), archive entry count limits (`POTENCIA_MAX_DOCX_ENTRIES=1000`), path traversal in archive member names (`..`, leading slashes, drive letters), and macro-enabled files (`vbaProject.bin`).
- **Secure object storage:** Restrictive permissions (`0o600` on files, `0o700` on directories), content-addressed SHA-256 keys, storage root boundary enforcement, zero internal storage paths exposed in API responses, strict tenant isolation (`404` for unauthorized users), and immediate cleanup of stored files on processing failure.
- **Docker & Compose configuration:** Added `clamav` container (`clamav/clamav:latest`, port 3310, health check) to `docker-compose.yml`, updated `.env.example` with `POTENCIA_CLAMAV_*` and `POTENCIA_MAX_*` settings.
- **Comprehensive security test suite:** 30 automated security tests in `backend/tests/test_secure_document_processing.py`. Total backend test suite now 195 tests, all passing hermetically.

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
| KI-4 | No malware scanning on uploads | Resolved | Integrated ClamAV daemon malware scanning (INSTREAM protocol) with fail-closed production mode and EICAR detection in Phase 21 |
| KI-5 | No email verification flow | Resolved | Implemented email verification and secure password recovery with SHA-256 hashed tokens and SMTP delivery in Phase 23 |
| KI-6 | OCR engine not installed | Resolved | Integrated Tesseract OCR and OpenCV preprocessing for scanned resumes in Phase 22 |
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
