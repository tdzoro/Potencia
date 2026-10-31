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

## Document handling

- Extension **and** magic bytes are checked; a `.pdf` containing PNG bytes is rejected with `415`.
- Upload size is enforced while streaming, not after buffering, so a large body is never held in memory.
- Files are stored content-addressed (`sha256`) under `POTENCIA_STORAGE_ROOT`, outside the database and outside any public path.
- Exports are stored under a separate `exports/` prefix so deleting an export can never unlink an uploaded document that hashes to the same bytes.
- Deletion is a cascade: removing a resume removes its analyses, matches, recommendations, revisions and exports.

## Downloads

An export download URL is an HMAC-signed capability: `export_id`, owner `user_id` and an expiry are signed with the server secret. It is valid for 15 minutes, bound to one file and one account, and a forged or transplanted token returns the same `404` as a missing export.

## Transport and browser defences

Every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, a `default-src 'none'` CSP, a restrictive `Permissions-Policy`, and `Cache-Control: no-store`. HSTS is added when the request arrives over HTTPS.

CORS is an explicit origin allow-list from `POTENCIA_CORS_ORIGINS`. A wildcard with credentials is never used.

## Rate limiting

Limits follow `docs/API.md §4`: 5 attempts / 15 min on login and registration, 10 / h on uploads, 20 / h on analyses and matches, 30 / h on exports, 300 / h overall. Identity is the account when a valid token is present, otherwise the client IP. Exceeding a limit returns `429` with `Retry-After`.

> **Limitation, stated plainly:** counters live in process memory. A multi-worker deployment needs a shared store (Redis) or each worker will enforce its own budget. Nothing else about the design changes.

## What is deliberately not done

| Area | Status | Why |
|:--|:--|:--|
| LLM provider | Not wired | Recommendations are deterministic rules. A model cannot invent an achievement because no model is in the request path. The provider seam (`app/ai/providers`) exists and validates any rewrite against a schema before use. |
| Prompt injection | Not applicable yet | No document text is sent to an external model. The design note remains in `ARCHITECTURE.md` so it is not lost when a provider is added. |
| Malware scanning | Not integrated | Uploads are type-checked and size-capped but not scanned. A production deployment should add ClamAV or an equivalent in front of the parser. |
| Email verification | Field exists, flow does not | `users.email_verified` is stored and returned; no mail is sent. |
| Audit log | Structured request logging only | Method, path, status and duration are logged with a request id. Resume contents, emails and tokens are never logged. |

## Incident surface

Error responses use one envelope with a documented code, a human message, optional field details and a request id. Stack traces and driver messages never reach the client; they are logged server-side against that id.

## Retention

Exports expire after 24 hours: `python -m app.tasks.retention` deletes expired files and rows. Uploaded documents are retained until the owner deletes them or deletes the account. There is no automatic expiry for uploaded documents, which is a product decision, not an oversight.

## Reporting

Security issues should be reported privately to the repository owner rather than opened as a public issue.
