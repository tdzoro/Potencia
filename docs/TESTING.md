# Testing

## Running the suites

```bash
cd backend && pytest -q          # 258 tests collected; 253 pass, 5 optional integrations skip
cd frontend && npm test          # 33 component/form tests (Vitest)
cd frontend && npm run build     # strict typecheck + production build
cd frontend && npm run e2e       # 15 browser journeys, needs a live stack
```

The default backend suite needs no PostgreSQL, no network and no AI provider: it runs on an in-memory SQLite database per test, with uploads in a temporary directory. Four ClamAV integration tests and the live Gemini call are opt-in and skip in that run. The browser suite needs a running API and a built web app; it seeds its own account, so it never depends on data already in a database.

## Backend

| Area | File | Behaviour asserted |
|:--|:--|:--|
| Health and errors | `test_health.py` | Envelope shape, request-id provenance, degraded database reporting |
| Authentication | `test_auth.py` | Registration, login, refresh, logout, identical failures for unknown email and wrong password, token-version revocation |
| Document pipeline | `test_document.py` | Extension and magic-byte validation, size limits, text-layer extraction, empty and scanned documents, page counts |
| Parsing | `test_parser.py` | Section detection, contact extraction, date normalisation, confidence, refusal to invent missing fields |
| Scoring | `test_scoring.py` | Criterion arithmetic, applicability (missing ≠ zero), determinism, score/impact reconciliation |
| ATS | `test_ats.py` | Table, column, image-only and scanned hazards; estimate bounds; disclaimer text |
| Resumes API | `test_resumes_api.py` | Upload → parse → analyse → report, cross-user isolation, disguised files, cascade delete |
| Matching | `test_matching.py` | Requirement bucketing (`need` vs `nice to have`), four skill states, year arithmetic, determinism |
| Recommendations and revisions | `test_recommendations.py` | Evidence on every card, idempotent generation, accept/reject/edit, metric gaps asked not invented, revision 0 immutability, foreign parent rejected |
| Exports | `test_exports.py` | Downloaded PDFs and DOCX re-opened and searched for the real score and content, newest revision exported by default, a chosen version exported instead of the newest, a version from another resume rejected without leaving a failed row, report/version pairing rejected, tampered token rejected |
| Security | `test_security.py` | Rate limiting with `Retry-After`, security headers, no internal leakage |
| Idempotency | `test_idempotency.py` | Replay returns the original body and creates nothing, keys are per account, cross-endpoint reuse is `409`, short keys are `422`, expiry allows reuse |
| Pagination | `test_pagination.py` | Pages walk without gaps or repeats, newest first, malformed cursor is `422` |
| Rate-limit store | `test_ratelimit_store.py` | Middleware honours an injected store, in-memory window, Redis `INCR`+`EXPIRE NX` semantics, unreachable Redis degrades |
| Calibration | `test_calibration.py` | Spearman on monotone and tied data, applicability-aware totals, normalisation |
| Performance | `test_performance.py` | Heading table ordered once at import, 1,400 classifications inside a loose budget, one document read per match (not one per requirement), 40-requirement match inside budget, eight-document parse inside budget, normalisation actually cached |
| Versions | `test_versions.py` | Labels stored and returned, unlabelled stays null, malformed `parent_id` is `422` not `500`, over-length label rejected, field-level comparison including projects and education, identical versions report no changes, cross-resume and cross-account comparison is `404` |
| Retention | `test_retention.py` | Expired file and row both removed, download link stops serving, unexpired export survives, an expired row without bytes still goes |
| Document hardening | `test_secure_document_processing.py` | Magic bytes, path traversal, ZIP-bomb ratio, encrypted PDFs, macros, EICAR detection, fail-closed scanning |
| OCR fallback | `test_ocr.py` | Text-layer bypass, scanned-page detection, Tesseract line-boundary preservation, preprocessing, confidence aggregation, low-confidence warning, timeout |
| Verification and recovery | `test_verification_and_recovery.py` | Hashed tokens, expiry, replay, non-enumerating responses, reset flow |
| Tenant isolation | `test_tenant_isolation.py` | A second user gets `404` on every resource of the first, across resumes, revisions, analyses, jobs, matches and exports |
| Migrations | `test_migrations.py` | Programmatic Alembic `upgrade → downgrade → upgrade` round trip |
| AI provider | `test_gemini_provider.py` | Schema validation, prompt-injection delimiting, rate-limit and timeout fallbacks; a live call only when a key is supplied |
| ATS boundaries | `test_ats_boundaries.py` | Bounds `[0, 100]` and reconciliation on empty, single-word and oversized documents |

## Tests that would fail if the product lied

- **Score reconciliation** — `sum(findings.score_impact) == 100 - overall` within 0.15.
- **Evidence required** — every finding must carry at least one verbatim excerpt.
- **No invented metrics** — a recommendation about an unquantified bullet either proposes text containing no digits, or asks the user for the real figure.
- **Partial is not absent** — a skill listed but not demonstrated is `partial`; a skill nowhere in the document is `absent`.
- **Original is immutable** — after a revision is saved, revision 0 is byte-identical.
- **Idempotency creates nothing** — a replayed create must not add a second row.

### Live ClamAV integration

CI starts a ClamAV daemon and runs the four real scanner integration tests separately from the hermetic suite. Locally, with clamd reachable on port 3310:

```bash
cd backend
POTENCIA_TEST_CLAMAV=1 POTENCIA_CLAMAV_ENABLED=true POTENCIA_CLAMAV_HOST=127.0.0.1 POTENCIA_CLAMAV_PORT=3310 .venv/bin/python -m pytest tests/test_clamav_integration.py -q
```

These exercise a clean PDF, the daemon's EICAR detection over `INSTREAM`, the upload path, and scanner settings.

## Browser suite

`frontend/e2e/journey.spec.ts` drives the real UI in Chrome:

| Test | What it proves |
|:--|:--|
| Landing copy and sign-in link | A visitor can reach authentication |
| Guard on `/app` | An unauthenticated visitor is redirected to `/login` |
| Dashboard | The stored score is rendered, not a placeholder |
| Report | Score, ATS section and priority actions are present |
| Recommendation | Accept persists across a reload |
| Export | A generated report exposes a signed `token=` link |
| Match | A pasted description produces an estimate and names `Terraform` as a gap |
| Studio | A summary edit saves as a new revision |
| Version comparison | A version is named, appears in the version picker, and the comparison names `summary` as the changed field with the new text |
| Version export | The named version is selectable on the export screen, generates a file, and the export history labels it with that version |
| History | The uploaded resume and its analysis are listed |

The suite found a real gap when first run: the landing page had no route to sign-in. The fix was in the application, not the test.

## Migrations

`test_migrations.py` runs `upgrade head → downgrade -1 → upgrade head` programmatically against SQLite on every suite run, which catches a migration that is missing, out of order or irreversible. CI repeats the round trip against a real PostgreSQL 16 service container, where the dialect differences actually live.

```bash
cd backend
POTENCIA_DATABASE_URL=postgresql+psycopg://potencia:potencia@localhost:5432/potencia alembic upgrade head
```

## Calibration

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/calibrate.py
```

Parses eight fixtures, scores them, and compares weight vectors by rank correlation. It writes `assets/readme/calibration.json`. The dataset is rubric-assigned, not recruiter-ranked — the script says so, because the difference matters.

## README artefacts

Every figure in the README comes from a script, and the graphs are rendered from the JSON those scripts wrote — a chart cannot disagree with the table beside it.

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/readme_charts.py

# Needs the API and a built web app: it seeds an account and runs the journey
API_BASE_URL=http://127.0.0.1:8010 WEB_URL=http://127.0.0.1:4173 \
  node scripts/capture_screenshots.mjs

# Page one of a real generated report PDF, rendered with PyMuPDF
PYTHONPATH=backend:. backend/.venv/bin/python scripts/report_page.py
PYTHONPATH=backend backend/.venv/bin/python scripts/measure_ocr.py  # requires Tesseract
```

`readme_charts.py` measures nothing; it reads `metrics.json`, `load.json`, `engine_profile.json` and `calibration.json`. `measure_ocr.py` builds a reproducible synthetic scan and measures real extraction, word recovery and score drift; its output is `assets/readme/ocr_profile.json`. `capture_screenshots.mjs` drives the real UI in Chromium — upload, analysis, job match, an accepted recommendation, a named version, two exports — and screenshots each screen, so an image cannot show a screen that does not work. `report_page.py` seeds its own account, exports an analysis report and rasterises its first page, so the README shows the artefact a user downloads rather than a mock of it.

The demo account can be seeded against a running API with `PYTHONPATH=backend backend/.venv/bin/python scripts/seed_demo.py --base http://127.0.0.1:8010`. The landing-page CTA is gated behind a demo build: build the frontend with `VITE_DEMO_MODE=1`; the email and password can be overridden with `VITE_DEMO_EMAIL` and `VITE_DEMO_PASSWORD`. Never enable demo mode unless the shared account is intended to be accessible to visitors.

Measurements are taken with the CPU boosted: on an idling laptop the same code reports 2.7 ms for a parse it measures at 0.84 ms at full clock, which is host state, not a regression. The scripts report what they observe and the README quotes the ratio where the absolute number would mislead.

## Frontend checks

`npm test` runs 33 Vitest + Testing Library tests across four files: login, registration, verification and recovery forms; upload validation and the OCR badge; the studio empty state and editor; recommendations, AI regeneration and export links.

`npm run typecheck` is the gate: `src/types/domain.ts` mirrors `docs/API.md`, so a contract drift breaks compilation instead of surfacing as a blank panel at runtime. `npm run build` runs it before bundling.

## Load test

```bash
# limiter off, so the run measures parsing and scoring rather than the throttle
POTENCIA_RATE_LIMIT_ENABLED=false uvicorn app.main:app --port 8010
PYTHONPATH=backend backend/.venv/bin/python scripts/load_test.py --base-url http://127.0.0.1:8010
```

Each worker registers, uploads one document, then posts analyses — real extraction, real parsing, real scoring. Result of the recorded run: 200 analyses over 8 clients in 3.31 s, **60.5 analyses/s**, p50 90.4 ms, p95 129.7 ms, p99 189.1 ms, max 207.8 ms, 0 failures. Stored in `assets/readme/load.json`.

This is one host, one API process and one local PostgreSQL. It catches a regression in the engine's cost; it is not a capacity plan.

## Known gaps

- Load figures come from one process on one host, so they bound engine cost and say nothing about multi-node scaling.
- No fuzzing of the document parsers beyond the malformed fixtures.
- OCR's end-to-end measurement uses one synthetic scan. It verifies the extraction path and reproducibility, not accuracy across real scanners and document conditions.
