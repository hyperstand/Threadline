# Threadline (M8)

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
| Hypothesis generation | Not implemented: no model is wired yet |
| Web UI | Pending (M9) |
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

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected: `{"status":"ok","version":"0.1.0","env":"dev",...}` plus an
`X-Threadline-Run-Id` response header.

The test suite runs offline. It needs no model credentials and no Goose binary.

## Typical workflow

```powershell
# Upload a runbook, scoped to the environment it applies to (curl.exe ships with Windows 10+)
curl.exe -F "file=@postgres-runbook.txt" -F "system_scope=postgres" -F "environment_scope=dev" http://127.0.0.1:8000/api/v1/documents

# Investigate a question against a named target
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/investigations -ContentType application/json `
  -Body '{"question":"postgres replication lag","target_system":"postgres","target_environment":"dev"}'
```

Routes (all under `/api/v1`):

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
- `THREADLINE_ENV=prod` requires `THREADLINE_API_TOKEN` and fails closed without it.

Database schema changes need the local SQLite file to be recreated until migrations
arrive. Delete the file under `data/` and restart.

## Known limitations

- `MAX_TOOL_CALLS` is loaded but not enforced yet (see the plan's M8 gaps).
- Normalized evidence is not persisted as separate records. Evidence lives in the report.
- No authentication beyond the production token check. Not for multi-user deployment.
- Applicability uses deterministic scope metadata only. It does not parse procedure
  prerequisites from document text.
