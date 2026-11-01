# POTENCIA — Phase 0 Repository Audit

**Repository:** `tdzoro/Potencia`
**Branch audited:** `main` @ `5262229` — *"Initial commit"*
**Date:** 2026-11-01
**Auditor:** Arghya Bose
**Phase exit criteria:** **PASS** — see §10

---

## 1. Scope and method

Phase 0 is inspection only. No application code, schema or configuration was created, deleted or modified during this audit.

What was actually done:

1. Cloned the default branch and enumerated every tracked file.
2. Read every tracked file in full (both of them).
3. Verified the actual commit history and branch topology.
4. Verified the GitHub collaborator's effective permissions through the API.
5. Probed the host toolchain — Node, npm, Python, pip, Docker, Compose, git, psql, redis — to determine what can be executed locally today.
6. Cross-checked the repository against the Master Product & Engineering Workflow to establish the gap between specification and reality.

Nothing was assumed from the workflow document. The findings below describe the repository as it exists.

---

## 2. Repository inventory

| Item | Finding |
|:--|:--|
| Tracked files | **2** — `LICENSE`, `README.md` |
| Commit history | **1** commit (`5262229`, "Initial commit") |
| Branches | `main` only (local + `origin/main`) |
| Frontend framework | **None** |
| Backend framework | **None** |
| Folder structure | **None** — flat root, no `frontend/`, `backend/`, `docs/`, `shared/`, `tests/` |
| API endpoints | **None** |
| Database configuration | **None** — no ORM, no models, no migrations, no connection string |
| AI integrations | **None** |
| Document processing | **None** |
| Dependency manifests | **None** — no `package.json`, `requirements.txt`, `pyproject.toml`, `poetry.lock` |
| Environment variables | **None** — no `.env`, no `.env.example` |
| Tests | **None** — no test runner, no fixtures, no CI configuration |
| Deployment configuration | **None** — no `Dockerfile`, no `docker-compose.yml`, no `.github/workflows/` |

### 2.1 `LICENSE`

Standard MIT text. **Copyright (c) 2026 MIM** — note the holder is `MIM`, while the repository owner is `tdzoro`. This is not an error to fix unilaterally (licence attribution is a legal decision), but it should be confirmed before the project is presented publicly or distributed.

**Resolved.** The holder confirmed the licence in Phase 19: the MIT text was replaced by an all-rights-reserved proprietary licence held by the POTENCIA Team. See [`LICENSE`](../LICENSE).

### 2.2 `README.md`

Two lines, 54 bytes:

```text
# Potential
Beyond Your Resume.Unleash Your Potential
```

Three defects, all cosmetic but visible on the project's front page:

- Project name rendered as **"Potential"** instead of **"POTENCIA"**.
- Missing space in **"Resume.Unleash"**.
- No product description, no architecture, no status, no setup, no documentation links.

**Resolved during this phase** — replaced with a full product and engineering README (§8.1).

---

## 3. Existing functionality report

**There is no executable functionality in this repository.**

This is not a broken or partially-built project. It is an empty project with a brand name attached. Consequently:

- No startup sequence exists to run or diagnose.
- No duplicate implementations, circular dependencies, missing imports, or unused dependencies can exist.
- No frontend routes can be broken because no router exists.
- No inconsistent data models exist because no models exist.

The practical consequence is favourable: **there is zero migration risk and zero legacy behaviour to preserve.** Every architectural decision in Phase 1 can be made on merit rather than around existing code. The workflow's instruction to "adapt the target structure to the existing repository" resolves to: adopt the target structure directly.

---

## 4. Environment audit

Host capability, verified rather than assumed:

| Tool | Version | Status |
|:--|:--|:--|
| Node | 22.16.0 | ✅ available |
| npm | 10.9.2 | ✅ available |
| Python | 3.12.3 | ✅ available |
| pip | 26.2.1 | ✅ available |
| git | 2.43.0 | ✅ available |
| Docker | 29.9.2 | ✅ available |
| Docker Compose | v5.6.1 | ✅ available |
| PostgreSQL (host) | — | ❌ not installed — **provision via Compose** |
| Redis (host) | — | ❌ not installed — **provision via Compose** |

**Implication for Phase 2:** the `psql` and `redis-server` binaries are absent, so any phase that assumes a host-installed database will fail locally. PostgreSQL and Redis must be supplied as Compose services from the outset; host installation is not a valid dependency.

**Permissions:** the acting collaborator holds `push: true`, `maintain: false`, `admin: false` on a public repository.

- ✅ Direct commits and pushes to `main` are possible.
- ✅ Branches and pull requests are possible.
- ❌ Repository **settings**, **Actions secrets**, branch protection rules and deployment environments require `admin`. Any phase needing CI secrets (Phase 16) requires the repository owner.

---

## 5. Technical debt

| ID | Debt | Severity | Disposition |
|:--|:--|:-:|:--|
| TD-1 | README is a two-line placeholder with a misspelled project name | High (public surface) | **Resolved** in this phase |
| TD-2 | No `.gitignore` — Python (`__pycache__`, `venv`, `.env`, `*.db`) and Node (`node_modules`, `dist`, `.vite`) artefacts will be committed on the first build | High | Phase 2, before the first dependency install |
| TD-3 | No `.env.example` — onboarding is undocumented and secrets handling is undefined | High | Phase 2 |
| TD-4 | No `Dockerfile` / `docker-compose.yml`, so there is no reproducible environment | Medium | Phase 2 |
| TD-5 | No CI, so no automated gate exists to detect a regression | Medium | Phase 2 |
| TD-6 | Licence holder (`MIM`) does not match repository owner (`tdzoro`) | Medium (legal, not technical) | **Resolved** in Phase 19 — proprietary licence held by the POTENCIA Team |
| TD-7 | No `CONTRIBUTING.md` / commit convention — contributor drift is likely on a shared repository | Low | Phase 2 |
| TD-8 | Brand assets absent from the repository | Medium | **Resolved** in this phase (§8.1) |

---

## 6. Security findings

No exploitable surface exists yet — no endpoints, no storage, no credentials, no dependencies. The audit therefore reports *pre-emptive* obligations rather than live vulnerabilities:

1. **Secret handling is not yet defined.** Until `.gitignore` and `.env.example` exist, there is a real risk that the first `.env` created during Phase 2 is committed. This is the single highest-probability security incident for a project at this stage, and TD-2 is the mitigation.
2. **No file-validation boundary exists yet.** Phase 4 must treat every uploaded document as hostile: extension is not proof of type, archives and embedded objects must be rejected, and size limits must be enforced before any parser touches the bytes.
3. **Prompt injection is an input class, not an edge case.** Resume text and job descriptions are attacker-controlled. Phase 9 must ensure document content is never interpreted as instructions.
4. **CORS is unconstrained by default.** Phase 2 must allow-list origins explicitly; a wildcard with credentials is not acceptable.
5. **No credential has been committed to this repository.** Verified — there is nothing in the tree to leak.

---

## 7. Architecture proposal

Given zero legacy constraints, adopt the workflow's target architecture without modification of intent, with the following concrete decisions:

**1. Deterministic-first, generation-second.** The scoring engine computes before any model is called. This makes scores reproducible and testable, keeps cost bounded, and means an AI provider outage degrades *explanation* — not the product.

**2. Strict module boundaries, enforced by directory, not convention.**
`document/` (bytes → text) → `intelligence/` (text → findings) → `ai/` (findings → prose) → `api/` (prose → HTTP). No module imports upward. The parser never knows what scoring does with its output.

**3. Provider abstraction at the AI boundary.** One internal interface; providers are adapters. Business logic never imports a vendor SDK, so a provider change is a configuration change.

**4. Guilty-until-proven data isolation.** Every repository call is scoped by `user_id` at the query level, not filtered after retrieval. Tests must prove a cross-user read fails, not merely that the happy path works.

**5. Versioned methodology.** Every stored analysis carries the scoring methodology version that produced it. Re-scoring an old analysis under new weights is then a deliberate, auditable act rather than silent score drift.

**6. Compose-first infrastructure.** PostgreSQL and Redis are services, never host prerequisites (§4). A new contributor runs one command to be functional.

No component is proposed that the product does not require. Specifically rejected at this stage: microservices, a message broker, model fine-tuning, a vector database, and a separate search engine. Each is plausible later; none is justified by a resume-analysis workload.

---

## 8. Work performed in this phase

### 8.1 Changes made

| File | Change |
|:--|:--|
| `assets/brand/potencia-logo.png` | Brand identity added. Re-encoded from source: metadata stripped, resampled to 1200×800 and optimized (1.46 MB → 708 KB) for repository weight and web use. |
| `README.md` | Replaced the placeholder with the product and engineering overview: identity, capability matrix, pipeline and architecture diagrams, scoring model, engineering principles, verified environment, honest phase status, privacy commitments and documentation index. |
| `docs/REPOSITORY_AUDIT.md` | This document. |
| `docs/PROJECT_STATUS.md` | Phase tracker initialised. |

Deliberately **not** created in this phase: `.gitignore`, `.env.example`, `Dockerfile`, `docker-compose.yml`, `package.json`, `requirements.txt`, any `frontend/` or `backend/` source. Those belong to Phases 1–2, and manufacturing them now would be the "build the entire application blindly" failure mode the workflow forbids.

### 8.2 What the README deliberately does not claim

The README describes the product's design and states plainly that it is at Phase 0. It contains no installation commands, no accuracy figures, and no "how it works today" claims, because no executable code exists. A README that advertises runnable software that cannot run is a defect, not marketing.

---

## 9. Recommended implementation sequence

| Order | Phase | Deliverable | Gate before proceeding |
|:-:|:--|:--|:--|
| 1 | **1** | `SRS.md`, `ARCHITECTURE.md`, `API.md`, `SCORING_METHODOLOGY.md` | Every endpoint has a defined request/response contract; scoring criteria are enumerable and testable |
| 2 | **2** | Working FastAPI + React skeleton, Compose stack, health check, CORS, logging, `.gitignore`, `.env.example` | Both apps start clean; frontend reaches backend health; no secret is trackable |
| 3 | **3** | User, resume, analysis, job, recommendation, revision models + auth | Register/login works; cross-user access is provably denied |
| 4 | **4** | PDF/DOCX extraction with confidence and OCR fallback | Fixtures across single/multi-column/scanned/malformed parse correctly or fail loudly |
| 5 | **5** | Structured resume representation + skill taxonomy | Fields trace to source text; nothing is inferred into existence |
| 6 | **6** | Deterministic scoring engine | Identical input → identical score; every deduction cites evidence |
| 7 | **7** | ATS compatibility engine | Findings reproducible across fixtures; labelled an estimate everywhere |
| 8 | **8** | Job matching | Deterministic aggregation; partial matches distinguished from false positives |
| 9 | **9** | Recommendation engine | Schema-validated output; factual-consistency tests; provider failure degrades gracefully |
| 10 | **10** | Improvement studio | Original preserved; revisions recoverable; concurrent edits safe |
| 11 | **11** | Full frontend on real APIs | No hardcoded results; loading/empty/error/retry states on every view |
| 12 | **12** | PDF/DOCX export | Generated files reopened programmatically and content-verified |
| 13 | **13** | Security & privacy hardening | No unresolved critical/high findings; `SECURITY.md` published |
| 14 | **14** | Full QA pass | End-to-end journey green; edge cases covered; failures disclosed |
| 15 | **15** | Performance profiling and optimization | Every optimization backed by a measurement |
| 16 | **16** | Production deployment | Clean-environment smoke test of the full user journey |

**Sequencing constraint:** Phase 4 gates everything downstream. A scoring engine built on unreliable extraction produces confidently wrong advice, which is worse than no advice. Phase 6 must not begin until parser fixtures pass.

---

## 10. Phase exit criteria

| Criterion | Result |
|:--|:-:|
| Repository fully inspected and documented | **PASS** |
| Existing functionality identified | **PASS** — none exists; recorded in §3 |
| Technical debt enumerated | **PASS** — 8 items, 3 resolved |
| Security posture assessed | **PASS** — 5 pre-emptive obligations, 0 live vulnerabilities |
| Dependencies and versions recorded | **PASS** — no project dependencies exist; toolchain verified in §4 |
| Deployment configuration assessed | **PASS** — none exists |
| Architecture proposed and justified | **PASS** — §7 |
| Implementation sequence defined with gates | **PASS** — §9 |
| No existing working functionality destroyed | **PASS** — placeholder README replaced by design |

**Exit criteria: PASS.**

**Blockers carried forward:** TD-6 (licence holder) needs an owner decision. Phase 16 CI secrets require repository `admin`, which this collaborator does not hold.

**Next phase:** Phase 1 — Product Specification & System Design.
