# Threadline — Implementation Plan (M1–M10 Tracker)

**Status:** Active — M8 complete (2026-10-14); M9 (minimal web UI) next
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

| Milestone | Scope (from SPEC §14 / PROMPT) | Depends on | Status | Acceptance | Result |
|---|---|---|---|---|---|
| M1 | Package, settings, health endpoint, SQLite foundation, tests | — | completed (2026-10-14) | `GET /health`, SQLite init, config validation | 17/17 (recorded) |
| M2 | Document ingestion with provenance (FR-01/02/10 partial) | M1 | implemented & tested (2026-10-14) | Upload PDF/DOCX/MD/TXT → chunks keep doc ID, hash, page/section; failure visible, never falsely `indexed` | 28/28 (recorded) |
| M3 | Keyword (FTS5) search + citation-backed answers (FR-03, FR-07 partial) | M2 | implemented & tested (2026-10-14) | FTS5 search, scoping/version filters, provenance, citation ID validation | 32/32 (recorded) |
| M4 | Vector retrieval + hybrid ranking behind interface (FR-03) | M3 | implemented & tested (2026-10-14) | In-memory vector adapter, hashing provider, hybrid RRF search, mode fallback, provenance/scores | 37/37 (recorded) |
| M5 | Three memory services + LangGraph checkpointing (FR-08/09/10) | M1, M4 | implemented & tested (2026-10-14) | Working/episodic/semantic managers, SQLite persistence, checkpoint resume, redaction, provenance-reviewed promotion | 42/42 (recorded) |
| M6 | Bounded investigation workflow with fake Goose (FR-04, FR-05 partial) | M5 | implemented & tested (2026-10-14) | LangGraph workflow, fake read-only Goose adapter, policy checks, working-state persistence, investigation API | 42/42 (recorded) |
| M7 | Real Goose CLI + read-only MCP/tool policy (FR-05/12) | M6 | implemented & tested (2026-10-14) | Config-gated MCP/JSON-RPC stdio adapter, read-only policy, timeouts, output limits, secret redaction, availability fallback | 47/47 (recorded) |
| M8 | Applicability checks + structured report + audit history (FR-06/07/11) | M6–M7 | **implemented & tested (2026-10-14)** | `confirmed/contradicted/unknown` (unknown ≠ confirmed; simulated results never confirm); typed FR-07 report with validated citations; audit events separate from memory; investigation history endpoint | 84/84 (full suite) |
| M9 | Minimal web UI | M8 | pending | Library/workspace/report/history screens; API usable without UI | — |
| M10 | Security + evaluation pass, reproducible setup | M1–M9 | pending | Prompt-injection, scope-escape, secret-redaction suites; eval metrics reported as measured, not claimed | — |

Results for M1–M7 are as recorded at the time. The full suite was re-run at the start
of M8 and passed 47/47 only after the blocking fixes listed below.

**Do not skip ahead.** Each milestone implements only its scope.

## Fixes applied at the start of M8 (2026-10-14)

The M1–M7 baseline did not run as recorded. These defects were found by running the
suite and reading the code, and were fixed before M8 work:

1. `src/threadline/audit/__init__.py` had a duplicated docstring, so `from __future__`
   was no longer first and the app failed to import.
2. `src/threadline/main.py` never imported the investigations router, so `create_app()`
   raised `NameError` at import.
3. `KnowledgeItemModel` had no `title` column, so `promote_knowledge` raised `TypeError`.
   Existing local SQLite files created before this change must be recreated (no
   migration tooling until PostgreSQL arrives).
4. `MemoryManager` accepted `vector_adapter` but never stored it. The hybrid search
   call raised `AttributeError`, which was swallowed, so `retrieve_knowledge` always
   returned nothing and investigations never saw any document passages.
5. The upload route did not accept `system_scope` / `environment_scope`, so no
   API-uploaded document could be scoped.
6. Investigation failures put raw exception text into the stored report. Failures now
   record a redacted audit event and store a fixed summary.

## M8 build notes

- **Applicability** (`evidence/verifier.py`, PRD FR-06): deterministic, no model.
  One check per document (scope from upload metadata), one per live observation
  (request envelope plus any scope the result itself declares), and `target_scope`.
  A mismatch contradicts. Missing metadata is unknown. Simulated results (adapter
  `fake`, see `SIMULATED_ADAPTER_NAMES`) never produce a confirmed check.
- **Report** (`evidence/models.py`, PRD FR-07): typed `InvestigationReport` covering
  request and scope, executive summary, observed facts with trust status, document
  references with applicability, applicability checks, hypotheses, next steps,
  risks and approvals, missing evidence, uncertainty, limitations, plan, disclaimer,
  run ID and timestamp. `validate_report_citations` rejects any cited ID that was not
  retrieved, failing closed.
- **Hypotheses** are an empty list. No model is wired, so none are generated. The
  report says so under missing evidence.
- **Audit** (PRD FR-11): `investigation.created`, `workflow.node_completed`,
  `workflow.node_failed`, `retrieval.failed`, `tool.invoked`, `tool.failed`,
  `applicability.assessed` (counts only), `investigation.resumed`, `investigation.failed`,
  `investigation.cancelled`, `investigation.finalized`. Writes are best-effort and
  logged on failure, so an audit error never crashes a run.
- **API:** `GET /api/v1/investigations?limit=` (history, newest first);
  `POST /api/v1/documents` accepts optional `system_scope` and `environment_scope` form
  fields; `mode` is validated as `live` or `document_only`.

## M8 known gaps (carried forward)

- `MAX_TOOL_CALLS` is loaded but never enforced. Bounded execution (PRD §9) needs a
  real budget check before M10.
- `normalize_evidence` builds normalized records but does not persist them (SPEC §7
  step 5). Evidence currently lives only in the report.
- `create_goose_adapter` returns the fake adapter when `GOOSE_ENABLED=false`, which is
  the default. Simulated results therefore appear in default-config reports, labelled
  as unverified. See the open decisions below.
- Route naming: SPEC §10 says `/investigations/{id}/events`; the implemented route is
  `/investigations/{id}/audit-events`.

## Requirements coverage (PRD FR-01–FR-13)

- FR-01 ingestion, FR-02 provenance, FR-03 retrieval: implemented (M2–M4).
- FR-04 orchestration: LangGraph workflow with bounded routing (M6). Budget enforcement is a gap above.
- FR-05 Goose/MCP: real adapter and read-only policy (M7); default is the fake adapter.
- FR-06 applicability, FR-07 report, FR-11 audit: implemented (M8).
- FR-08/09/10 memory: implemented (M5); episodes are labelled historical.
- FR-12 access and safety, FR-13 evaluation: exercised incrementally; full gate at M10.

## Conflicts / ambiguities log

1. `docs/` (task text) vs `threadline_docs/` (repo) — resolved: use
   `threadline_docs/` per user approval 2026-10-14.
2. SPEC §14 (11 steps) vs PROMPT M1–M10 — resolved: adopt M1–M10; SPEC steps
   fold into them (no behavioral conflict).
3. No substantive PRD/SPEC functional conflicts found.
4. PROMPT requires the README to match the implementation. README was stale (described
   M1 only) and has been updated for M8.

## Deferred decisions (need grounding or a user decision)

- **Default Goose mode (user decision needed):** with `GOOSE_ENABLED=false`, the app
  uses the fake adapter. Options: (a) keep it, with simulated results labelled as now;
  (b) default to document-only, so no simulated observations are produced outside tests.
- Exact OpenAI-compatible model and embedding model names — required before hypothesis
  generation (model wiring, not yet started).
- Production auth provider beyond `THREADLINE_API_TOKEN` fail-closed stub (M10).
- Document retention/deletion policy (M10).
- Postgres + pgvector migration trigger (post-MVP or on multi-user need). Schema changes
  before then need recreated local databases; migrations come with Alembic.
