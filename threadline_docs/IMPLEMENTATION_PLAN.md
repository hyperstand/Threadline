# Threadline — Implementation Plan (M1–M10 Tracker)

**Status:** Active — M1 in progress
**Sources:** `threadline_docs/PRD.md` (Draft v1.0), `threadline_docs/SPEC.md` (v1.0),
`threadline_docs/IMPLEMENTATION_PROMPT.md`
**Storage decision (approved):** SQLite + FTS5 local-first; vector optional behind a
replaceable interface; PostgreSQL + pgvector deferred.
**Model default (approved):** OpenAI-compatible via env vars; fakes in all tests.
**Goose mode (approved):** CLI subprocess adapter; verified in M7; fakes before that.
**Plan location (approved):** this file lives in `threadline_docs/` (task text says
`docs/`, repo uses `threadline_docs/` — recorded here instead of silently renaming).

> Do not recreate PRD/SPEC content here. This file tracks status, dependencies,
> acceptance, and deferred decisions only.

## Milestone status

| Milestone | Scope (from SPEC §14 / PROMPT) | Depends on | Status | Acceptance |
|---|---|---|---|---|
| M1 | Package, settings, health endpoint, SQLite foundation, tests | — | **completed (2026-10-14)** | `pytest -v` 17/17 passed | M2 |
| M2 | Document ingestion with provenance (FR-01/02/10 partial) | M1 | **implemented & tested (2026-10-14)** | Upload PDF/DOCX/MD/TXT → chunks keep doc ID, hash, page/section; failure visible, never falsely `indexed` | 28/28 tests pass |
| M3 | Keyword (FTS5) search + citation-backed answers (FR-03, FR-07 partial) | M2 | **implemented & tested (2026-10-14)** | FTS5 search, scoping/version filters, provenance, citation ID validation; tests 32/32 pass | M4 |
| M4 | Vector retrieval + hybrid ranking behind interface (FR-03) | M3 | **implemented & tested (2026-10-14)** | In-memory vector adapter, hashing provider, hybrid RRF search, mode fallback, provenance/scores; tests 37/37 pass | M5 |
| M5 | Three memory services + LangGraph checkpointing (FR-08/09/10) | M1, M4 | **implemented & tested (2026-10-14)** | Working/episodic/semantic managers, SQLite persistence, checkpoint resume, redaction, provenance-reviewed promotion; tests 42/42 pass | M6 |
| M6 | Bounded investigation workflow with fake Goose (FR-04, FR-05 partial) | M5 | **implemented & tested (2026-10-14)** | LangGraph workflow, fake read-only Goose adapter, policy checks, working-state persistence, investigation API and audit/events; tests 42/42 pass | M7 |
| M7 | Real Goose CLI + read-only MCP/tool policy (FR-05/12) | M6 | **implemented & tested (2026-10-14)** | Config-gated real MCP/JSON-RPC adapter, read-only policy, timeouts, output limits, secret redaction, availability fallback; tests 47/47 pass | M8 |
| M8 | Applicability checks + structured report + audit/history (FR-06/07/11) | M6–M7 | pending | `confirmed/contradicted/unknown` (unknown ≠ confirmed); report schema per PRD FR-07; audit separate from memory |
| M9 | Minimal web UI | M8 | pending | Library/workspace/report/history screens; API usable without UI |
| M10 | Security + evaluation pass, reproducible setup | M1–M9 | pending | Prompt-injection, scope-escape, secret-redaction suites; eval metrics reported as measured, not claimed |

**Do not skip ahead.** Each milestone implements only its scope.

## Requirements coverage (PRD FR-01–FR-13)

- Implemented after M1: none fully; M1 provides the foundation (config, health,
  storage bootstrap, test harness) only.
- M2→M10 mapping is in the table above. FR-12 (access/safety) and FR-13
  (evaluation) are exercised incrementally, with the full gate at M10.

## Dependencies and architectural decisions (M1)

- Python ≥3.11, FastAPI + Pydantic v2 + SQLAlchemy 2.x, `pydantic-settings`,
  `pytest` + `httpx` (TestClient). **No LangChain/LangGraph in M1** (deferred to M5).
- No Goose integration in M1 (deferred to M6 fake / M7 real).
- SQLite file at `DATABASE_URL` (default `sqlite:///./data/threadline.db`);
  directory auto-created; `:memory:` supported for tests.
- M1 accepts **only** `sqlite:` URLs and rejects others with an actionable error
  (PostgreSQL comes later — this is intentional, not a bug).
- Production (`THREADLINE_ENV=prod`) fails closed without `THREADLINE_API_TOKEN`.
- Run/request IDs (UUID hex) logged per request and returned as
  `X-Threadline-Run-Id`; secrets redacted from logs/errors via a shared helper.

## Next milestone detail (M1 — this build)

Scope: `pyproject.toml`, `src/threadline/{main,config,persistence/database}`,
`.env.example`, `Dockerfile`, `docker-compose.yml`, `README.md`,
`tests/unit + tests/integration`, run `pytest -v` until green.
Out of scope: ingestion, retrieval, memories, graph, Goose, UI, eval dataset.

## Tests required for M1

- Config defaults load; invalid `DATABASE_URL` rejected with actionable,
  secret-free message; prod-without-token fails closed; redaction helper masks
  `password/token/api_key/bearer` values.
- SQLite init creates file + `app_meta` table, is idempotent, rejects
  uncreatable paths actionably.
- `GET /health` → 200 with `status/version/env`; `X-Threadline-Run-Id` header
  present; body contains no secrets; unknown route → 404.

## Conflicts / ambiguities log

1. `docs/` (task text) vs `threadline_docs/` (repo) — resolved: use
   `threadline_docs/` per user approval 2026-10-14.
2. SPEC §14 (11 steps) vs PROMPT M1–M10 — resolved: adopt M1–M10; SPEC steps
   fold into them (no behavioral conflict).
3. No substantive PRD/SPEC functional conflicts found.

## Deferred decisions (need grounding before their milestone)

- Exact OpenAI-compatible embedding model name (M4).
- Goose CLI version + JSON I/O schema to verify against (M7) — no Goose binary
  on PATH at M1 time.
- Production auth provider beyond `THREADLINE_API_TOKEN` fail-closed stub (M8/M10).
- Document retention/deletion policy (M2/M10).
- Postgres + pgvector migration trigger (post-MVP or on multi-user need).
