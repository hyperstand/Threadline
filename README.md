# Threadline (M1 skeleton)

Evidence-driven operational knowledge and investigation agent.
M1 provides project config, `GET /health`, SQLite foundation, and tests only.

Spec: `threadline_docs/PRD.md`, `threadline_docs/SPEC.md`,
`threadline_docs/IMPLEMENTATION_PROMPT.md`.
Plan: `threadline_docs/IMPLEMENTATION_PLAN.md`.

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

## Configuration

See `.env.example`. M1 supports `sqlite:` `DATABASE_URL` values only; other
schemes fail with an actionable error. `THREADLINE_ENV=prod` requires
`THREADLINE_API_TOKEN` (fail closed).

## Docker (optional)

```powershell
docker compose up --build
```

## Scope note

M1 only: no ingestion, retrieval, memories, LangGraph, Goose, UI, or eval set.
LangChain/LangGraph and Goose arrive at M5–M7 per the plan.
