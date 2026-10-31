# Testing

## Running the suites

```bash
cd backend && pytest -q          # 140 tests, hermetic
cd frontend && npm run build     # strict typecheck + production build
cd frontend && npm run e2e       # 10 browser tests, needs a live stack
```

The backend suite needs no PostgreSQL, no network and no AI provider: it runs on an in-memory SQLite database per test, with uploads in a temporary directory. The browser suite needs a running API and a built web app; it seeds its own account, so it never depends on data already in a database.

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
| Exports | `test_exports.py` | Downloaded PDFs and DOCX re-opened and searched for the real score and content, newest revision exported, tampered token rejected |
| Security | `test_security.py` | Rate limiting with `Retry-After`, security headers, no internal leakage |
| Idempotency | `test_idempotency.py` | Replay returns the original body and creates nothing, keys are per account, cross-endpoint reuse is `409`, short keys are `422`, expiry allows reuse |
| Pagination | `test_pagination.py` | Pages walk without gaps or repeats, newest first, malformed cursor is `422` |
| Rate-limit store | `test_ratelimit_store.py` | Middleware honours an injected store, in-memory window, Redis `INCR`+`EXPIRE NX` semantics, unreachable Redis degrades |
| Calibration | `test_calibration.py` | Spearman on monotone and tied data, applicability-aware totals, normalisation |
| Versions | `test_versions.py` | Labels stored and returned, unlabelled stays null, malformed `parent_id` is `422` not `500`, over-length label rejected, field-level comparison, identical versions report no changes, cross-resume and cross-account comparison is `404` |
| Retention | `test_retention.py` | Expired file and row both removed, download link stops serving, unexpired export survives, an expired row without bytes still goes |

## Tests that would fail if the product lied

- **Score reconciliation** — `sum(findings.score_impact) == 100 - overall` within 0.15.
- **Evidence required** — every finding must carry at least one verbatim excerpt.
- **No invented metrics** — a recommendation about an unquantified bullet either proposes text containing no digits, or asks the user for the real figure.
- **Partial is not absent** — a skill listed but not demonstrated is `partial`; a skill nowhere in the document is `absent`.
- **Original is immutable** — after a revision is saved, revision 0 is byte-identical.
- **Idempotency creates nothing** — a replayed create must not add a second row.

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
| History | The uploaded resume and its analysis are listed |

The suite found a real gap when first run: the landing page had no route to sign-in. The fix was in the application, not the test.

## Migrations

The backend suite does not exercise Alembic. CI applies `upgrade head → downgrade base → upgrade head` against a real PostgreSQL 16 service container, which catches a migration that is missing, out of order or irreversible.

```bash
cd backend
POTENCIA_DATABASE_URL=postgresql+psycopg://potencia:potencia@localhost:5432/potencia alembic upgrade head
```

## Calibration

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/calibrate.py
```

Parses eight fixtures, scores them, and compares weight vectors by rank correlation. It writes `assets/readme/calibration.json`. The dataset is rubric-assigned, not recruiter-ranked — the script says so, because the difference matters.

## Frontend checks

`npm run typecheck` is the gate: `src/types/domain.ts` mirrors `docs/API.md`, so a contract drift breaks compilation instead of surfacing as a blank panel at runtime. `npm run build` runs it before bundling.

## Load test

```bash
# limiter off, so the run measures parsing and scoring rather than the throttle
POTENCIA_RATE_LIMIT_ENABLED=false uvicorn app.main:app --port 8010
PYTHONPATH=backend backend/.venv/bin/python scripts/load_test.py --base-url http://127.0.0.1:8010
```

Each worker registers, uploads one document, then posts analyses — real extraction, real parsing, real scoring. Result of the recorded run: 200 analyses over 8 clients in 2.59 s, **77.4 analyses/s**, p50 72.3 ms, p95 142.8 ms, p99 155.8 ms, 0 failures. Stored in `assets/readme/load.json`.

This is one host, one API process and one local PostgreSQL. It catches a regression in the engine's cost; it is not a capacity plan.

## Known gaps

- Load figures come from one process on one host, so they bound engine cost and say nothing about multi-node scaling.
- No fuzzing of the document parsers beyond the malformed fixtures.
- OCR has no installed engine, so that path is untested end to end (the detection and reporting around it is tested).
