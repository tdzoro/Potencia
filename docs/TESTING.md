# Testing

## Running the suite

```bash
cd backend
python -m pytest tests -q
```

108 tests. The suite is hermetic: an in-memory SQLite database per test, no PostgreSQL, no network, no AI provider. Uploads land in a temporary directory that is deleted with the process.

The schema under test is the same `Base.metadata` Alembic reads, so a model change that is not migrated still shows up here — but migrations themselves are verified separately (below).

## What is covered

| Area | File | Behaviour asserted |
|:--|:--|:--|
| Health and errors | `test_health.py` | Envelope shape, request-id provenance, degraded database reporting |
| Authentication | `test_auth.py` | Registration, login, refresh, logout, identical failures for unknown email and wrong password, token-version revocation |
| Document pipeline | `test_document.py` | Extension and magic-byte validation, size limits, extraction of text layers, empty and scanned documents, page counts |
| Parsing | `test_parser.py` | Section detection, contact extraction, date normalisation, confidence, refusal to invent missing fields |
| Scoring | `test_scoring.py` | Criterion-level arithmetic, applicability (missing ≠ zero), determinism, score/impact reconciliation |
| ATS | `test_ats.py` | Table, column, image-only and scanned hazards; estimate bounds; disclaimer text |
| Resumes API | `test_resumes_api.py` | Upload → parse → analyse → report, cross-user isolation, disguised files, cascade delete |
| Matching | `test_matching.py` | Requirement bucketing, matched/partial/weakly-demonstrated/absent states, year arithmetic, determinism |
| Recommendations & revisions | `test_recommendations.py` | Evidence on every card, idempotent generation, accept/reject/edit, metric gaps asked not invented, revision 0 immutability, foreign parent rejection |
| Exports | `test_exports.py` | Downloaded PDFs and DOCX re-opened and searched for the real score and content, newest revision exported, tampered token rejected |
| Security | `test_security.py` | Rate limiting with `Retry-After`, security headers, no internal leakage |

## Tests that would fail if the product lied

A few assertions exist specifically because the easy implementation is the dishonest one:

- **Score reconciliation** — `sum(findings.score_impact) == 100 - overall` within 0.15. If the findings stop explaining the number, this fails.
- **Evidence required** — every finding must carry at least one verbatim excerpt.
- **No invented metrics** — a recommendation about an unquantified bullet either proposes text with no digits, or asks the user for the real figure.
- **Partial is not absent** — a skill listed but not demonstrated is `partial`; a skill nowhere in the document is `absent`. Collapsing them would tell people to add skills they have.
- **Original is immutable** — after a revision is saved, revision 0 is byte-identical.

## Migrations

The suite does not exercise Alembic. CI applies `upgrade head → downgrade base → upgrade head` against a real PostgreSQL 16 service container, which catches a migration that is missing, out of order or irreversible.

Locally:

```bash
cd backend
POTENCIA_DATABASE_URL=postgresql+psycopg://potencia:potencia@localhost:5432/potencia \
  alembic upgrade head
```

## Frontend

```bash
cd frontend
npm run typecheck   # strict, noUncheckedIndexedAccess and noUnusedLocals on
npm run build
```

The typecheck is the gate: the API payload types in `src/types/domain.ts` mirror `docs/API.md`, so a contract drift breaks compilation rather than surfacing as a blank panel at runtime.

## End-to-end

`scripts/readme_metrics.py` drives a live instance through the whole journey — register, upload, analyse, recommend, revise, export, match — and writes the measurements used in the README. If a stage breaks, that script fails and the numbers cannot be regenerated.

## Known gaps

- No browser automation suite; the frontend is verified by typecheck, build and a headless render of every route.
- No load testing. The latency figures are single-user measurements on a local PostgreSQL container.
- No fuzzing of the document parsers beyond the malformed fixtures.
