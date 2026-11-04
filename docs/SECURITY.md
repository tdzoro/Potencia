# Security & Privacy

POTENCIA processes documents that contain a person's full contact details, employment history and education. This document states what is protected, how, and what is **not** yet handled.

## Authentication

| Control | Implementation |
|:--|:--|
| Password storage | bcrypt, per-password salt, cost factor from the library default |
| Password policy | 12 characters minimum, enforced on registration and password reset |
| Access token | JWT, HS256, 15-minute lifetime, `type: access` claim |
| Refresh token | JWT, 14-day lifetime, bound to a per-account `token_version` |
| Revocation | Logout and password reset bump `token_version`, instantly invalidating every refresh token for the account |
| Enumeration defence | Constant-time execution: login failure returns identical `401`; forgot-password and resend-verification return identical `200` generic success notices |
| Email verification | 24-hour cryptographically secure random token (`secrets.token_urlsafe(32)`), stored strictly as SHA-256 hash |
| Password recovery | 60-minute cryptographically secure random token, stored strictly as SHA-256 hash, single-use enforcement |

Tokens are signed with `POTENCIA_SECRET_KEY`. The application **refuses to start** with `POTENCIA_ENVIRONMENT=production` and the development placeholder secret.

## Email Verification & Password Recovery

Implemented in Phase 23 to secure account lifecycles and recovery:

### Cryptographic Token Storage
- **Never store raw tokens:** Registration and password recovery generate 32-byte URL-safe cryptographic tokens (`secrets.token_urlsafe(32)`).
- **Hashed storage:** Tokens are hashed using SHA-256 (`hashlib.sha256(token.encode()).hexdigest()`) before database insertion into the `auth_tokens` table. Even with full database access, raw tokens cannot be recovered or stolen.
- **Strict Lifecycles:** Each token specifies `expires_at` (24h for email verification, 60m for password reset) and `used_at`.
- **Single-Use Enforcement:** Tokens can be consumed exactly once. When consumed or replaced, `used_at` is timestamped and any previously pending tokens of the same type for that user are invalidated.

### Session Revocation on Password Reset
- Resetting a password updates `user.password_hash` with bcrypt and immediately increments `user.token_version`.
- Any existing refresh tokens embedding the old `token_version` are instantly rejected on the next refresh attempt (`401 Session Revoked`), evicting any compromised or stale sessions across all devices.

### Anti-Enumeration & Privacy
- `POST /api/v1/auth/forgot-password` always returns `200 OK` with a generic message (`"If an account exists with that email address, password reset instructions have been sent."`), regardless of whether the email is registered.
- `POST /api/v1/auth/resend-verification` always returns `200 OK` with a generic message (`"If an unverified account exists for that email, a verification link has been sent."`), whether the account is unverified, already verified, or unregistered.
- For unregistered accounts, dummy bcrypt timing equalisation ensures requests take equivalent wall-clock time, defeating timing attacks.

### Email Delivery Engine (`app/services/email_service.py`)
- Standard SMTP transport over TLS/SSL (port 465 or 587) with optional authentication.
- Responsive, branded HTML + plain text dual MIME formatting.
- **Fail-Safe Operation:** SMTP connection failures or timeouts are caught, logged without leaking credentials or tokens, and do not crash user requests.
- **Hermetic Development/Testing:** When `SMTP_HOST` is unset, sent emails are recorded in an in-memory queue (`_SENT_EMAILS`) for unit testing without network dependencies.

## Authorisation and data isolation

Every owned table carries `user_id` at row level, including tables reachable only through a parent. Ownership is enforced in the query layer rather than by a join, so there is no join to forget.

A request for another account's resource returns `404`, never `403`: whether a resource exists is itself private.

### Multi-Tenant Isolation Test Suite (`backend/tests/test_tenant_isolation.py`)
Automated in Phase 24 to guarantee regression-proof row-level isolation across all entity endpoints:
- Two distinct authenticated tenants (User A and User B) are provisioned.
- User A creates resumes, revisions, analyses, recommendations, jobs, matches, and exports.
- User B attempts to read, edit, delete, or cross-match against each of User A's entities.
- Asserted behavior: all cross-tenant requests strictly return HTTP `404 Not Found` with `{ "error": { "code": "not_found" } }`.
- Cross-tenant match creation (User B attempting to match their resume against User A's job) returns `404`.
- Cross-tenant export creation (User B attempting to export User A's analysis) returns `404`.

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
10. **Extract document text:** Text layers extracted using PyMuPDF (PDF) or python-docx (DOCX). For scanned or image-dominant PDFs, automatically engages the OpenCV preprocessing pipeline and Tesseract OCR engine with word-level confidence scoring.
11. **Validate extracted content:** Unparseable or empty documents are flagged with appropriate error metadata.
12. **Automatic failure cleanup:** If text extraction or database persistence fails after storing, the uploaded file is immediately unlinked from object storage to prevent orphaned files.


### OCR & Computer Vision Security
- **Strict Pre-Execution Gate:** OCR executes strictly after file size checks, extension/magic-byte validation, and ClamAV malware scanning. Malicious files never reach the OCR engine.
- **Resource & Memory Bounds:** Multi-page rendering enforces the maximum page limit (`POTENCIA_MAX_PDF_PAGES=50`) and renders at 200 DPI. Bitmaps and pixmaps are released page-by-page to prevent memory exhaustion.
- **Processing Timeouts:** Per-page and total document timeouts (`POTENCIA_OCR_TIMEOUT_SECONDS`, default 30s) prevent denial-of-service from adversarial or complex scanned images.
- **In-Memory Operations:** Preprocessing and OCR operate strictly in-memory without creating unmanaged temporary image files on disk.
- **Confidence Transparency:** Low-quality or degraded scans trigger an explicit `ocr_low_confidence` warning to prevent unreliable analysis.

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
| Email verification & recovery | Integrated (Phase 23) | Complete verification and recovery flows via SMTP, cryptographic random tokens hashed with SHA-256 in `auth_tokens`, and `token_version` session revocation. |
| Audit log | Structured request logging only | Method, path, status and duration are logged with a request id. Resume contents, emails and tokens are never logged. |

## Incident surface

Error responses use one envelope with a documented code, a human message, optional field details and a request id. Stack traces and driver messages never reach the client; they are logged server-side against that id.

## Retention

Exports expire after 24 hours: `python -m app.tasks.retention` deletes expired files and rows. Uploaded documents are retained until the owner deletes them or deletes the account. There is no automatic expiry for uploaded documents, which is a product decision, not an oversight.

## Reporting

Security issues should be reported privately to the repository owner rather than opened as a public issue.
