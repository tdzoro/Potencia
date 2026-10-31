# POTENCIA — API Contract

**Version:** `v1`
**Status:** authoritative. Implementation in Phases 3–12 must conform; divergence requires amending this document first.
**Base path:** `/api/v1`

---

## 1. Conventions

### 1.1 Transport

- HTTPS only in non-development environments.
- `Content-Type: application/json` except `POST /resumes`, which is `multipart/form-data`.
- All timestamps are ISO 8601 UTC with an explicit offset (`2026-11-01T09:14:03Z`).
- All identifiers are opaque UUIDv7 strings. Clients must not infer ordering or meaning from them.
- All lists are paginated (see §1.5) — there is no unpaginated collection endpoint.

### 1.2 Versioning

The version lives in the path. A breaking change requires `/v2`; additive, optional fields do not. Clients must ignore unknown fields — this is what makes additions non-breaking.

### 1.3 Authentication

`Authorization: Bearer <access_token>` on every endpoint except `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh` and `GET /health`.

- Access token: JWT, HS256, **15 minute** TTL.
- Refresh token: opaque, hashed at rest, **14 day** TTL, single-use with rotation.
- Claims: `sub` (user id), `iat`, `exp`, `jti`, `type` (`access` | `refresh`).
- Missing or invalid token → `401 unauthenticated`. Never `403`; a client must be able to distinguish "log in again" from "you may not do this".

**Authorization is applied inside the data-access layer, not after retrieval.** Every query is scoped by the authenticated `user_id`. A cross-user read must return `404 not_found`, never `403` — the existence of another user's resource is itself information.

### 1.4 Error envelope

Every non-2xx response returns exactly this shape. No endpoint returns a bare string or an unhandled framework error.

```json
{
  "error": {
    "code": "validation_error",
    "message": "Human-readable summary, safe to display.",
    "details": [
      { "field": "file", "issue": "exceeds_max_size", "meta": { "max_bytes": 5242880 } }
    ],
    "request_id": "req_01JCM8W3Z9"
  }
}
```

| Code | HTTP | Meaning |
|:--|:-:|:--|
| `validation_error` | 400 / 422 | Malformed request body or parameters |
| `unauthenticated` | 401 | Missing, expired or invalid credentials |
| `forbidden` | 403 | Authenticated but action not permitted (e.g. revoked token) |
| `not_found` | 404 | Resource absent **or** not owned by the caller |
| `method_not_allowed` | 405 | The path exists but not for this HTTP method |
| `conflict` | 409 | State conflict (duplicate email, stale revision) |
| `file_rejected` | 422 | Upload failed validation; `details` names the reason |
| `payload_too_large` | 413 | Exceeds size limit; rejected before parsing |
| `unsupported_media_type` | 415 | Not a PDF or DOCX by content, not by extension |
| `rate_limited` | 429 | `Retry-After` header present |
| `dependency_unavailable` | 502 / 503 | Database or AI provider unreachable; `details[].dependency` names it |
| `internal_error` | 500 | Unexpected failure. **Never** leaks a stack trace, SQL, path or provider payload |

`request_id` is echoed in the `X-Request-ID` response header and appears in structured logs, so a user-reported failure is traceable without resume contents ever being logged.

**One documented exception.** `GET /health` is a probe rather than a resource. It keeps its health fields at the top level on both `200` and `503`, so monitoring reads it directly instead of unwrapping an envelope, and *additionally* carries an `error` object in the shape above when degraded. Every other endpoint — including every `/api/v1` route — uses the envelope for all non-2xx responses.

### 1.5 Pagination

Cursor-based, not offset — offsets shift under concurrent writes.

```
GET /resumes?limit=20&cursor=eyJpZCI6...
```

```json
{ "items": [ ... ], "next_cursor": "eyJpZCI6..." , "has_more": true }
```

`limit` defaults to 20, maximum 100. `next_cursor` is `null` on the final page.

### 1.6 Idempotency

`POST /resumes`, `POST /analyses`, `POST /matches` and `POST /exports` are all guarded by `X-Idempotency-Key`. A repeated key within 24 hours returns the original response with `200` and `Idempotency-Replayed: true`. Without this, a double-submit on a slow connection bills a user twice for the same analysis.

### 1.7 Long-running work

Document extraction, analysis, matching and export are asynchronous. They return `202 Accepted` with a resource in a non-terminal state, and clients poll the resource.

```json
{ "status": "queued" }
```

`status` ∈ `queued` | `running` | `completed` | `failed` | `cancelled`. A `failed` resource carries `failure: { code, message, retryable }`. Clients must treat `retryable: false` as terminal.

---

## 2. Data objects

### 2.1 `User`

```json
{
  "id": "018f...",
  "email": "user@example.com",
  "display_name": "Arghya Bose",
  "created_at": "2026-11-01T09:14:03Z",
  "email_verified": false
}
```

`password_hash` never appears in any response. Neither does any token.

### 2.2 `TokenPair`

```json
{
  "access_token": "eyJ...",
  "refresh_token": "rt_...",
  "token_type": "bearer",
  "expires_in": 900
}
```

### 2.3 `Resume`

```json
{
  "id": "018f...",
  "original_filename": "arghya-resume.pdf",
  "media_type": "application/pdf",
  "size_bytes": 184320,
  "page_count": 2,
  "status": "completed",
  "extraction": {
    "confidence": 0.94,
    "method": "text_layer",
    "ocr_used": false,
    "text_chars": 4180,
    "warnings": []
  },
  "structure": { "...": "see §2.4" },
  "created_at": "2026-11-01T09:14:03Z"
}
```

`extraction.method` ∈ `text_layer` | `ocr` | `partial`. `extraction.warnings` is never silently empty when extraction degraded — that would be a fabricated success.

### 2.4 `ResumeStructure`

The parsed representation. Every field traces to source text.

```json
{
  "contact": { "name": null, "email": null, "phone": null, "links": [] },
  "summary": { "text": null, "confidence": "high" },
  "sections": [
    {
      "kind": "experience",
      "heading_as_written": "WORK EXPERIENCE",
      "items": [
        {
          "title": "Backend Intern",
          "organisation": "Acme",
          "start": "2025-06",
          "end": "2025-08",
          "date_precision": "month",
          "bullets": [ { "text": "Built ...", "span": [1204, 1311] } ]
        }
      ]
    }
  ],
  "skills": { "explicit": ["Python"], "inferred": [ { "name": "FastAPI", "basis": "stated in experience bullet 3" } ] },
  "uncertain": [ { "field": "education[0].end", "reason": "date_ambiguous" } ]
}
```

**`uncertain` is mandatory to respect.** A field that could not be determined is `null` and, if it matters, listed here. Filling it with a plausible guess is a product defect, not a convenience.

`section.kind` ∈ `summary` | `experience` | `education` | `skills` | `projects` | `certifications` | `achievements` | `leadership` | `other`.

`date_precision` ∈ `day` | `month` | `year`. Presence flags (`"present"`) are represented as `end: null` with `date_precision: "present"`.

### 2.5 `Scores`

```json
{
  "methodology_version": "1.0.0",
  "overall": 68.4,
  "applicable_weight": 85,
  "components": {
    "content_quality":        { "value": 62.0, "weight": 25, "confidence": "medium" },
    "experience":             { "value": 71.5, "weight": 20, "confidence": "high" },
    "skills":                 { "value": 66.0, "weight": 15, "confidence": "medium" },
    "structure":              { "value": 80.0, "weight": 15, "confidence": "high" },
    "ats_compatibility":      { "value": 74.0, "weight": 15, "confidence": "high" },
    "language_readability":   { "value": 61.0, "weight": 10, "confidence": "low" }
  },
  "job_match": null
}
```

- `value` ∈ `[0, 100]`, one decimal place. Never a bare integer — precision claims must not exceed evidence.
- **Applicability:** when a component is not applicable it is **absent**, and `applicable_weight` reflects the reduced denominator. Absent ≠ zero.
- `job_match` is a separate object (§2.8) and is **never** blended into `overall`. A resume is not worse for targeting a different role.
- `confidence` ∈ `low` | `medium` | `high`, derived from extraction confidence and evidentiary density (see `SCORING_METHODOLOGY.md` §7).

### 2.6 `Finding`

The atom of every report. Nothing actionable exists outside a finding.

```json
{
  "id": "f_018f...",
  "category": "content_quality",
  "criterion": "CQ-03",
  "severity": "high",
  "title": "Three experience bullets contain no measurable outcome",
  "evidence": [
    { "section": "experience[0].bullets[2]", "text": "Worked on the backend API." }
  ],
  "explanation": "The bullet states an activity, not a result. Recruiters cannot judge scope or impact from it.",
  "remediation": "Add the scale you worked at: dataset size, request volume, latency, team size — whichever is true.",
  "score_impact": -4.5
}
```

`severity` ∈ `critical` | `high` | `medium` | `low` | `info`. `score_impact` is the exact deduction this finding contributed; it is present only for findings produced by the scoring engine, and `null` for ATS-only findings.

**Evidence is mandatory.** A finding with no `evidence` array is a bug: it is unfalsifiable advice.

### 2.7 `ATSReport`

```json
{
  "estimate": 74.0,
  "disclaimer": "ATS compatibility estimate. Not a prediction of screening outcomes.",
  "checks": [
    {
      "id": "ATS-07",
      "label": "Multi-column layout detected",
      "status": "warn",
      "severity": "medium",
      "evidence": [ { "page": 1, "text": "two text columns spanning 780px" } ],
      "explanation": "Column order can be reassembled incorrectly by simpler parsers, scrambling dates against roles.",
      "remediation": "Use a single-column layout, or ensure each role's dates sit on the same line as the title."
    }
  ],
  "summary": { "pass": 9, "warn": 4, "fail": 1 }
}
```

`status` ∈ `pass` | `warn` | `fail`. `disclaimer` is a required field, not frontend copy — it ships with the data so it cannot be omitted by a client.

**Document-parse compatibility and job-keyword relevance are reported separately.** Merging them produces a number nobody can act on.

### 2.8 `JobMatch`

```json
{
  "methodology_version": "1.0.0",
  "estimate": 61.0,
  "requirements": {
    "required_skills": [ { "name": "PostgreSQL", "status": "matched", "evidence": ["experience[1].bullets[0]"] } ],
    "preferred_skills": [ { "name": "Kubernetes", "status": "absent", "evidence": [] } ],
    "experience_years": { "required": 3, "demonstrated": 2, "status": "partial" },
    "education": { "required": "B.Tech", "status": "matched" },
    "responsibilities": [ { "text": "Own the data pipeline", "status": "weakly_demonstrated" } ]
  },
  "gaps": [ { "name": "Kubernetes", "advice": "Not present in the resume. Do not add it unless you have used it." } ]
}
```

`status` ∈ `matched` | `partial` | `weakly_demonstrated` | `absent`.

**Three states must never collapse into two.** "Absent from the resume", "possibly present but not stated", and "demonstrated with evidence" are different facts, and conflating them is exactly how products end up telling people to add skills they do not have.

### 2.9 `Recommendation`

```json
{
  "id": "r_018f...",
  "analysis_id": "018f...",
  "category": "experience_bullet",
  "priority": "high",
  "finding_id": "f_018f...",
  "original_text": "Worked on the backend API.",
  "proposed_text": "Owned the backend API for the billing service.",
  "reason": "Converts an activity statement into ownership.",
  "requires_user_input": [
    { "field": "scale", "question": "What scale did the billing service operate at — requests/day or records?" }
  ],
  "confidence": "medium",
  "state": "pending"
}
```

`category` ∈ `summary` | `experience_bullet` | `project_description` | `achievement` | `skills_organisation` | `grammar` | `clarity` | `relevance` | `keyword_placement` | `formatting`.
`state` ∈ `pending` | `accepted` | `rejected` | `edited`.

**`proposed_text` must be factually implied by `original_text`.** If improving a bullet requires a metric that is not in the resume, `proposed_text` stays conservative and `requires_user_input` carries the question. A fabricated "improved" bullet is worse than a weak original, because the user may believe it.

### 2.10 `Revision`

```json
{
  "id": "rev_018f...",
  "resume_id": "018f...",
  "parent_id": "rev_018e...",
  "content": { "...": "approved resume structure" },
  "applied_recommendations": ["r_018f..."],
  "created_at": "2026-11-01T09:20:00Z"
}
```

Revision `0` is always the untouched parse. The original is immutable; every edit creates a new node. `parent_id` makes the chain explicit, so history is a tree, not a guess.

### 2.11 `Export`

```json
{
  "id": "exp_018f...",
  "kind": "improved_resume",
  "format": "pdf",
  "status": "completed",
  "size_bytes": 92311,
  "download_url": "https://.../exports/exp_018f.../download?token=...",
  "expires_at": "2026-11-01T09:35:00Z"
}
```

`kind` ∈ `analysis_report` | `improved_resume`. `format` ∈ `pdf` | `docx`.
`download_url` is short-lived (15 minutes) and single-user. **Internal storage paths and provider URLs never appear in a response.**

---

## 3. Endpoints

### 3.1 Health

| Method | Path | Auth | Description |
|:--|:--|:-:|:--|
| `GET` | `/health` | — | Liveness plus dependency status |

```json
{
  "status": "ok",
  "version": "0.1.0",
  "environment": "development",
  "dependencies": { "database": "ok" },
  "uptime_seconds": 412
}
```

`status` ∈ `ok` | `degraded`. A database that cannot be reached yields **`503` with `status: "degraded"` and `dependencies.database: "unavailable"`** — the app keeps serving so the failure is observable rather than a dead port. `200` is only returned when every required dependency is reachable.

### 3.2 Authentication

| Method | Path | Auth | Success |
|:--|:--|:-:|:--|
| `POST` | `/auth/register` | — | `201` `{ user, tokens }` |
| `POST` | `/auth/login` | — | `200` `TokenPair` |
| `POST` | `/auth/refresh` | refresh token | `200` `TokenPair` |
| `POST` | `/auth/logout` | access | `204` — revokes the presented refresh token |
| `GET` | `/auth/me` | access | `200` `User` |
| `DELETE` | `/users/me` | access | `204` — deletes account and all owned data |

Request bodies:

```json
// register
{ "email": "user@example.com", "password": "...", "display_name": "Arghya Bose" }
// login
{ "email": "user@example.com", "password": "..." }
// refresh
{ "refresh_token": "rt_..." }
```

Rules: password minimum 12 characters, checked against a breach corpus in Phase 13; duplicate email → `409 conflict`; wrong credentials → `401` with the **same message and timing** as unknown email, so account existence is not enumerable.

### 3.3 Resumes

| Method | Path | Auth | Success |
|:--|:--|:-:|:--|
| `POST` | `/resumes` | access | `201` `Resume` (`status: queued`) |
| `GET` | `/resumes` | access | `200` paginated `Resume` |
| `GET` | `/resumes/{resume_id}` | access | `200` `Resume` |
| `DELETE` | `/resumes/{resume_id}` | access | `204` — deletes file, parse and dependent analyses |
| `POST` | `/resumes/{resume_id}/revisions` | access | `201` `Revision` |
| `GET` | `/resumes/{resume_id}/revisions` | access | `200` paginated `Revision` |

`POST /resumes` is `multipart/form-data` with a single field `file`.

Validation order — **cheapest and safest first, before any parser reads the bytes**:

1. `Content-Length` ≤ 5 MiB → else `413`.
2. Declared extension ∈ `{.pdf, .docx}` → else `415`.
3. Magic bytes confirm the declared type (`%PDF-`; DOCX = ZIP with `[Content_Types].xml`) → else `415 unsupported_media_type`.
4. Structural integrity; reject encrypted, macro-bearing or archive-bomb inputs → `422 file_rejected`.

Extension is never trusted on its own. A file named `resume.pdf` that is not a PDF is rejected.

### 3.4 Analyses

| Method | Path | Auth | Success |
|:--|:--|:-:|:--|
| `POST` | `/analyses` | access | `202` `Analysis` (`status: queued`) |
| `GET` | `/analyses` | access | `200` paginated `Analysis` |
| `GET` | `/analyses/{analysis_id}` | access | `200` `Analysis` with scores and findings |
| `GET` | `/analyses/{analysis_id}/report` | access | `200` aggregated report |
| `DELETE` | `/analyses/{analysis_id}` | access | `204` |

```json
// POST /analyses
{ "resume_id": "018f...", "job_id": "018e..." }
```

`job_id` is optional. With it, the report gains `job_match`; without it, `job_match` is `null`.

`scores.overall` is **identical with or without a job description**. The six intrinsic components already sum to a weight of 100 (`SCORING_METHODOLOGY.md` §2), so there is nothing to renormalise, and a candidate is neither rewarded nor penalised for targeting a role.

```json
// GET /analyses/{id}
{
  "id": "018f...",
  "resume_id": "018f...",
  "job_id": null,
  "status": "completed",
  "scores": { "...": "§2.5" },
  "ats": { "...": "§2.7" },
  "findings": [ { "...": "§2.6" } ],
  "strengths": [ { "text": "Quantified 7 of 9 experience bullets.", "evidence": ["experience[0].bullets[1]"] } ],
  "priority_actions": ["...ordered by score_impact descending..."],
  "methodology_version": "1.0.0",
  "failure": null,
  "created_at": "2026-11-01T09:14:03Z",
  "completed_at": "2026-11-01T09:14:41Z"
}
```

`strengths` entries require evidence exactly as findings do. Praise without citation is filler.

### 3.5 Job descriptions

| Method | Path | Auth | Success |
|:--|:--|:-:|:--|
| `POST` | `/jobs` | access | `201` `Job` |
| `GET` | `/jobs` | access | `200` paginated `Job` |
| `GET` | `/jobs/{job_id}` | access | `200` `Job` |
| `DELETE` | `/jobs/{job_id}` | access | `204` |

```json
{ "title": "Backend Engineer", "company": "Acme", "description": "..." }
```

`title` and `company` are optional labels for the user's own list; matching uses `description` only. Presenting a company label as a hiring signal would be inventing data.

### 3.6 Matching

| Method | Path | Auth | Success |
|:--|:--|:-:|:--|
| `POST` | `/matches` | access | `202` `Match` (`status: queued`) |
| `GET` | `/matches/{match_id}` | access | `200` `Match` |

```json
{ "resume_id": "018f...", "job_id": "018e..." }
```

### 3.7 Recommendations

| Method | Path | Auth | Success |
|:--|:--|:-:|:--|
| `GET` | `/analyses/{analysis_id}/recommendations` | access | `200` paginated `Recommendation` |
| `POST` | `/recommendations/{recommendation_id}/decision` | access | `200` `Recommendation` |

```json
{ "decision": "edit", "edited_text": "Owned billing API for 40k daily requests." }
```

`decision` ∈ `accept` | `reject` | `edit`. One endpoint with an explicit enum replaces separate accept/reject routes: same capability, one state machine, no divergence.

`edited_text` is required when `decision = "edit"` and ignored otherwise. Decisions are idempotent — replaying the same decision returns the current state rather than erroring.

### 3.8 Exports

| Method | Path | Auth | Success |
|:--|:--|:-:|:--|
| `POST` | `/exports` | access | `202` `Export` (`status: queued`) |
| `GET` | `/exports/{export_id}` | access | `200` `Export` |
| `GET` | `/exports/{export_id}/download` | signed URL | `200` binary |

```json
{ "analysis_id": "018f...", "kind": "improved_resume", "format": "pdf" }
```

Download is authorized by the signed token in `download_url`, bound to the owning user and expiring in 15 minutes. Guessing an export id must not yield a file.

---

## 4. Rate limits

| Scope | Limit |
|:--|:--|
| `POST /auth/login`, `POST /auth/register` | 5 / 15 min per IP + per email |
| `POST /resumes` | 10 / hour per user |
| `POST /analyses`, `POST /matches` | 20 / hour per user |
| `POST /exports` | 30 / hour per user |
| All other authenticated routes | 300 / hour per user |

Limits are per user where authenticated, since IP is a poor identity behind NAT. Exceeding a limit returns `429` with `Retry-After` and the standard error envelope.

---

## 5. Contract obligations

Every endpoint, without exception:

1. Authenticates where required and scopes data access to the caller inside the query.
2. Validates input against a Pydantic schema before touching a service.
3. Declares a response schema — no free-form dictionaries leak from the database to the wire.
4. Returns the §1.4 envelope on failure, with a `request_id`.
5. Emits a structured log entry keyed by `request_id` containing endpoint, status, duration and user id — **never** resume text, job description text, filenames, or tokens.
6. Has an automated test covering its success path, its validation failure path and its authorization failure path.

The frontend is a consumer of this contract only. It holds no AI credentials, no storage paths, and no business rules that duplicate server-side scoring.
