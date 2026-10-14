# Threadline (M9)

Evidence-driven operational knowledge and investigation agent.

Threadline answers operational questions from indexed runbooks and manuals, checks
whether each procedure applies to the target environment, and produces a report where
every claim traces to a stored document passage or a recorded observation. Conclusions
are marked as observed, source-backed, unverified, or unknown. Generated
recommendations are not proof of a diagnosis.

Spec: `threadline_docs/PRD.md`, `threadline_docs/SPEC.md`,
`threadline_docs/IMPLEMENTATION_PROMPT.md`.
Plan and status: `threadline_docs/IMPLEMENTATION_PLAN.md`.

## Status

| Area | State |
|---|---|
| Documents: upload (PDF, DOCX, MD, TXT), provenance, optional system/environment scope | Implemented |
| Retrieval: FTS5 keyword search, hybrid ranking with an in-memory vector adapter (optional) | Implemented |
| Memory: working (checkpoints), episodic (labelled historical), semantic | Implemented |
| Investigation workflow: bounded LangGraph with per-node audit | Implemented |
| Live evidence: Goose over MCP, read-only policy | Implemented; off by default |
| Applicability checks, structured report, audit history | Implemented (M8) |
| Web UI: Library, Workspace, History, Report | Implemented (M9) |
| Hypothesis generation | Not implemented: no model is wired yet |
| Authentication | Not implemented: no route enforces a token |
| Security and evaluation suites, PostgreSQL | Pending (M10) |

## Local setup

Requires Python ≥ 3.11.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"
Copy-Item .env.example .env
pytest -v
uvicorn threadline.main:app --reload --port 8000
```

The test suite runs offline. It needs no model credentials and no Goose binary.

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected: `{"status":"ok","version":"0.1.0","env":"dev",...}` plus an
`X-Threadline-Run-Id` response header.

## Web UI

Open **http://127.0.0.1:8000/** in a browser:

- **Library:** upload a document with optional system and environment scope, and list
  the indexed documents.
- **Workspace:** ask a question about a target system and environment. Choose live
  evidence or documents only.
- **History:** recent investigations, newest first.
- **Report:** one investigation in full, with an on-demand audit trail.

The UI calls the same API, so it needs no extra setup. It has no authentication, so run
it on a local machine only.

## Typical workflow

```powershell
# Upload a runbook, scoped to the environment it applies to (curl.exe ships with Windows 10+)
curl.exe -F "file=@postgres-runbook.txt" -F "system_scope=postgres" -F "environment_scope=dev" http://127.0.0.1:8000/api/v1/documents

# Investigate a question against a named target
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/investigations -ContentType application/json `
  -Body '{"question":"postgres replication lag","target_system":"postgres","target_environment":"dev"}'
```

Routes:

- `GET /`: the web UI. Static files are served under `/ui/`.
- `GET /health`: liveness and version.
- Under `/api/v1`:
  - `POST /documents`, `GET /documents`, `GET /documents/{id}`
  - `POST /investigations` (`mode`: `live` or `document_only`), `GET /investigations?limit=`
    (history), `GET /investigations/{id}`, `POST .../resume`, `POST .../cancel`
  - `GET /investigations/{id}/report`, `.../evidence`, `.../audit-events`
  - `GET /search`, `POST /answers`

## Reading a report

- **Document references** carry an applicability status: `confirmed` when the document's
  scope matches the target, `contradicted` when it is scoped elsewhere, and `unknown` when
  it has no complete scope metadata. Unknown is never treated as confirmed.
- **Observed facts** come from live tools. A result with `simulated: true` came from the
  fake Goose adapter. It is labelled `unverified` and never confirms applicability.
- **Hypotheses** are empty. No model is wired in this build, and the report says so.
- **Audit events** record each workflow step, tool calls and failures, applicability
  results, and the final outcome, all with redacted metadata.

## Configuration

See `.env.example`. Key settings:

- `DATABASE_URL`: SQLite only in this build. Other schemes fail with an actionable error.
- `GOOSE_ENABLED`: defaults to `false`. In that case the app uses the **fake** Goose
  adapter, and its results are labelled simulated (see the open decision in the plan).
  Set `true` with `GOOSE_COMMAND` to use a real Goose MCP server. If that command is not
  available, the app runs document-only and records a limitation.
- `VECTOR_ENABLED`: optional in-memory vector retrieval.
- `THREADLINE_ENV=prod` requires `THREADLINE_API_TOKEN` at startup and fails closed
  without it. The token is not yet enforced on any route.

Database schema changes need the local SQLite file to be recreated until migrations
arrive. Delete the file under `data/` and restart.

## Project layout

```text
src/threadline/
  api/            HTTP routes and response schemas
  audit/          audit events, separate from memory
  evidence/       applicability verifier, report schema, citation validation
  ingestion/      document extraction, chunking, provenance
  integrations/   Goose adapters (fake and real MCP) and the read-only tool policy
  memory/         working, episodic, and semantic memory; checkpoints
  orchestration/  LangGraph investigation workflow and its nodes
  persistence/    SQLAlchemy models and database setup
  retrieval/      keyword (FTS5), vector, and hybrid search
  ui/             single-page web UI (index.html, app.css, app.js)
tests/
  unit/           unit tests for each module
  integration/    API and end-to-end tests
threadline_docs/  PRD, SPEC, implementation prompt, and the milestone plan
```

## Known limitations

- No authentication on any route, including the UI. Anyone who can reach the server can
  read documents, run investigations, and see audit events. Run locally only until a
  decision is made (see the plan's open decisions).
- `MAX_TOOL_CALLS` is loaded but not enforced yet. The plan's M8 gaps list this.
- Normalized evidence is not persisted as separate records. Evidence lives in the report.
- Observed-fact excerpts show the tool result as Python repr text, not formatted JSON.
- Applicability uses deterministic scope metadata only. It does not parse procedure
  prerequisites from document text.
- Hypothesis generation needs a model adapter, and none is wired in.
