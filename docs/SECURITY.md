# Security & Privacy

POTENCIA processes documents that contain a person's full contact details, employment history and education. This document states what is protected, how, and what is **not** yet handled.

## Authentication

| Control | Implementation |
|:--|:--|
| Password storage | bcrypt, per-password salt, cost factor from the library default |
| Password policy | 12 characters minimum, enforced on registration only |
| Access token | JWT, HS256, 15-minute lifetime, `type: access` claim |
| Refresh token | JWT, 14-day lifetime, bound to a per-account `token_version` |
| Revocation | Logout bumps `token_version`, invalidating every refresh token for the account |
| Enumeration defence | Unknown emails still run a bcrypt comparison against a cached dummy hash, and both failure paths return an identical `401` |

Tokens are signed with `POTENCIA_SECRET_KEY`. The application **refuses to start** with `POTENCIA_ENVIRONMENT=production` and the development placeholder secret.

## Authorisation and data isolation

Every owned table carries `user_id` at row level, including tables reachable only through a parent. Ownership is enforced in the query layer rather than by a join, so there is no join to forget.

A request for another account's resource returns `404`, never `403`: whether a resource exists is itself private.

## Document handling & Secure Ingestion Pipeline

Uploaded resumes undergo a strict 12-step validation and ingestion pipeline before reaching the parsing and scoring engines:

1. **Receive upload:** Streaming chunk read (`_read_limited`) rejects uploads exceeding 5 MiB without buffering large payloads in memory (`413 Payload Too Large`).
2. **Authenticate user:** Request is strictly bound to the authenticated user account.
3. **Validate request & idempotency:** Deduplicates requests using `X-Idempotency-Key`.
4. **Sanitize filename:** Strips POSIX and Windows path traversal sequences (`../`, `..\`), control characters, null bytes, and Windows reserved device names (`CON`, `NUL`, `PRN`), truncating to a maximum of 255 characters with safe fallbacks.
5. **Validate extension & file signature:** Checks file extension against allow-list (`.pdf`, `.docx`) and verifies magic bytes (`%PDF-` in the first 1 KiB, or `PK\x03\x04` for DOCX). Mismatched or fake extensions are rejected (`415 Unsupported Media Type`).
6. **Container structure validation:**
   - **PDF:** Rejects encrypted or password-protected PDFs (`needs_pass`), zero-page documents, PDFs exceeding 50 pages (`POTENCIA_MAX_PDF_PAGES`), and PDFs containing embedded executable or script attachments (`.exe`, `.bat`, `.vbs`, etc.).
   - **DOCX:** Strict in-memory ZIP inspection. Rejects archives missing `word/document.xml`, archives with macro files (`vbaProject.bin`), archives exceeding 1,000 entries (`POTENCIA_MAX_DOCX_ENTRIES`), path traversal sequences in entry names (`..`, leading `/` or `\`, drive letters), uncompressed expansions over 100 MiB, and ZIP bombs with compression ratios over 100:1.
7. **Malware scanning (ClamAV):**
   - Transmits document bytes to ClamAV daemon via the native `INSTREAM` protocol over TCP (no third-party dependencies).
   - Enforces configurable socket timeout (`POTENCIA_CLAMAV_TIMEOUT_SECONDS`, default 10s).
   - Fast-path detection of the standard EICAR test signature.
   - **Fail-Closed in Production:** If `POTENCIA_ENVIRONMENT=production` or `POTENCIA_CLAMAV_REQUIRED=true`, any ClamAV connection outage or timeout immediately fails closed with HTTP `503 Service Unavailable`, preventing unscanned files from reaching storage.
   - In local development mode with scanner unconfigured, logs a warning and falls back safely to test scanning.
8. **Malware rejection:** Files identified as malicious are rejected with HTTP `422 Unprocessable Entity` containing the threat classification, without persisting the bytes to disk.
9. **Secure storage:** Approved files are saved using content-addressed SHA-256 digests (`storage_key = {prefix}{digest[:2]}/{digest}.ext`) under `POTENCIA_STORAGE_ROOT`, outside web root and database. Storage files are created with restrictive permissions (`0o600` for files, `0o700` for directories). Internal storage paths and keys are never exposed in API responses.
10. **Extract document text:** Text layers extracted using PyMuPDF (PDF) or python-docx (DOCX).
11. **Validate extracted content:** Unparseable or empty documents are flagged with appropriate error metadata.
12. **Automatic failure cleanup:** If text extraction or database persistence fails after storing, the uploaded file is immediately unlinked from object storage to prevent orphaned files.

## Downloads

An export download URL is an HMAC-signed capability: `export_id`, owner `user_id` and an expiry are signed with the server secret. It is valid for 15 minutes, bound to one file and one account, and a forged or transplanted token returns the same `404` as a missing export.

## Transport and browser defences

Every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, a `default-src 'none'` CSP, a restrictive `Permissions-Policy`, and `Cache-Control: no-store`. HSTS is added when the request arrives over HTTPS.

CORS is an explicit origin allow-list from `POTENCIA_CORS_ORIGINS`. A wildcard with credentials is never used.

## Rate limiting

Limits follow `docs/API.md §4`: 5 attempts / 15 min on login and registration, 10 / h on uploads, 20 / h on analyses and matches, 30 / h on exports, 300 / h overall. Identity is the account when a valid token is present, otherwise the client IP. Exceeding a limit returns `429` with `Retry-After`.

Counters live behind a `LimitStore` interface (`app/core/ratelimit_store.py`):

- **Default** — in-process sliding window. Correct for one worker, and the API logs which mode it is in.
- **Shared** — set `POTENCIA_REDIS_URL` and install the `redis` extra; counters then live in Redis (`INCR` + `EXPIRE ... NX`, atomic and self-expiring) and every worker enforces one budget.

If a configured Redis is unreachable, the API logs an error and falls back to process memory rather than failing requests — a degraded limit is better than an outage, but it is never silent.

## AI Provider Security & Privacy (Google Gemini)

When `GEMINI_API_KEY` is configured, POTENCIA connects to Google Gemini (`gemini-2.5-flash` default) as an editorial writing assistant for recommendations. The integration adheres to strict data minimization, prompt-injection containment, and anti-hallucination rules:

### Data Sent to Gemini
- **Sent**: Only the specific sentence or bullet point being improved, the recommendation category, and the reason for the improvement.
- **NEVER sent**: Candidate names, email addresses, phone numbers, addresses, personal links, file names, raw document bytes, or complete resume bodies.

### Prompt Injection Safeguards
- All extracted resume text is treated as untrusted data, never as system instructions.
- Untrusted text is strictly enclosed in isolated `<untrusted_resume_content>` XML tags with closing-tag escaping.
- System instructions explicitly forbid the model from executing, obeying, or acknowledging any instructions, prompt overrides, or system commands found inside untrusted resume text.
- Output is constrained by server-side JSON schema enforcement via Pydantic (`_GeminiResponseSchema`).
- Output length is strictly capped (`max_output_tokens=1024`, schema length `max_length=2000`).
- No external code or tools are executable from model output.

### Anti-Hallucination & Non-Fabrication Rules
- Gemini is instructed to preserve factual meaning without inventing employers, dates, qualifications, degrees, skills, or certifications.
- Zero fabrication of numerical claims (percentages, revenue, user counts). If a bullet lacks quantification, the model formulates a prompt in `requires_user_input` asking the user for the real figure.
- An automated post-validation rule rejects any proposal that introduces new numerical digits when the source text contained none.

### Deterministic Engine Independence
- Gemini output is tagged `source: "gemini"` and acts solely as an advisory proposal.
- Gemini is never invoked during parsing, normalization, scoring, or ATS checking.
- Deterministic ATS scores, category weights, and resume revision 0 are completely invariant to model responses or provider outages.

## What is deliberately not done

| Area | Status | Why |
|:--|:--|:--|
| LLM scoring | Prohibited | Scores and findings are 100% deterministic rules. An LLM is used only as an optional text rewrite assistant (`app/ai/providers/gemini.py`). |
| Malware scanning | Integrated (Phase 21) | ClamAV `INSTREAM` protocol integration with fail-closed production guarantees and automated container service in docker-compose. |
| Email verification | Field exists, flow does not | `users.email_verified` is stored and returned; no mail is sent. |
| Audit log | Structured request logging only | Method, path, status and duration are logged with a request id. Resume contents, emails and tokens are never logged. |

## Incident surface

Error responses use one envelope with a documented code, a human message, optional field details and a request id. Stack traces and driver messages never reach the client; they are logged server-side against that id.

## Retention

Exports expire after 24 hours: `python -m app.tasks.retention` deletes expired files and rows. Uploaded documents are retained until the owner deletes them or deletes the account. There is no automatic expiry for uploaded documents, which is a product decision, not an oversight.

## Reporting

Security issues should be reported privately to the repository owner rather than opened as a public issue.
