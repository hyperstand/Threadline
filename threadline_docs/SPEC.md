# Threadline --- Technical Specification

**Version:** 1.0\
**Status:** Draft implementation baseline\
**Language:** Python\
**Primary architecture:** FastAPI + LangGraph + LangChain + Goose/MCP\
**Memory design:** Working, episodic, semantic; audit/trace is separate

## 1. Architecture overview

Threadline is a modular application with these logical layers:

1.  API and UI.
2.  Investigation orchestration (LangGraph).
3.  Knowledge retrieval (LangChain-facing adapter plus hybrid
    retriever).
4.  Goose/MCP integration for approved operational evidence.
5.  Memory services: working, episodic, semantic.
6.  Evidence normalization and applicability verification.
7.  Audit/trace.
8.  Persistence.

The initial deployment may use one backend process and one database.
Logical boundaries should be maintained in code even if infrastructure
is shared.

## 2. Proposed repository layout

``` text
threadline/
├── README.md
├── pyproject.toml
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── alembic.ini
├── migrations/
├── docs/
│   ├── PRD.md
│   ├── SPEC.md
│   ├── SECURITY.md
│   └── EVALUATION.md
├── src/threadline/
│   ├── main.py
│   ├── config.py
│   ├── api/
│   │   ├── routes_documents.py
│   │   ├── routes_investigations.py
│   │   ├── routes_reports.py
│   │   └── schemas.py
│   ├── orchestration/
│   │   ├── graph.py
│   │   ├── state.py
│   │   ├── nodes.py
│   │   └── policies.py
│   ├── ingestion/
│   │   ├── extractors.py
│   │   ├── chunking.py
│   │   └── pipeline.py
│   ├── retrieval/
│   │   ├── interfaces.py
│   │   ├── hybrid.py
│   │   ├── keyword.py
│   │   └── vector.py
│   ├── memory/
│   │   ├── manager.py
│   │   ├── working.py
│   │   ├── episodic.py
│   │   └── semantic.py
│   ├── integrations/
│   │   ├── models.py
│   │   ├── goose.py
│   │   └── mcp.py
│   ├── evidence/
│   │   ├── models.py
│   │   ├── verifier.py
│   │   └── citations.py
│   ├── audit/
│   │   ├── events.py
│   │   └── repository.py
│   ├── persistence/
│   │   ├── database.py
│   │   └── repositories.py
│   └── evaluation/
│       └── runner.py
└── tests/
    ├── unit/
    ├── integration/
    ├── security/
    └── evaluation/
```

Do not create empty abstractions for every file just to match the tree.
Implement modules when their behavior is required, and keep interfaces
small.

## 3. Technology choices

### Backend

-   Python with FastAPI and Pydantic.
-   SQLAlchemy 2.x or an equivalent explicit persistence layer.
-   Alembic for schema migrations when PostgreSQL is used.
-   pytest for automated tests.

### AI and orchestration

-   LangChain for model integrations, document/retrieval primitives, and
    structured outputs where useful.
-   LangGraph for the investigation state machine, checkpoints,
    conditional routing, bounded loops, and resumability.
-   Do not create an unconstrained autonomous loop.
-   Use one coordinator graph initially; helper nodes can be ordinary
    Python functions.

### Goose

-   Integrate the actual Goose application through a supported,
    documented interface.
-   Prefer MCP for tool interoperability where supported by the deployed
    Goose version.
-   Do not assume Goose is a Python library or import Goose internals.
-   Keep Goose behind an adapter and provide a fake implementation for
    tests.
-   Configure the permitted MCP tools explicitly. The MVP exposes
    read-only tools only.

### Persistence and search

Recommended shared deployment: - PostgreSQL for application records,
documents/chunks, episodes, evidence, and audit events. - pgvector for
semantic search. - PostgreSQL full-text search or BM25-compatible
implementation for keyword retrieval.

Lightweight local development alternative: - SQLite for application
state, episode records, and audit records. - SQLite FTS5 for keyword
search. - A replaceable vector adapter; vector search may be optional
initially. - Do not imply that SQLite FTS5 provides semantic search.

Avoid committing to two production storage backends simultaneously.
Define repository/retriever interfaces and choose one primary
implementation for the first release. PostgreSQL + pgvector is the
recommended default if the goal is a shared web application; SQLite is
appropriate for a local-only proof of concept.

### Frontend

-   Next.js + TypeScript is the proposed web UI.
-   The backend API and CLI/tests should remain usable without the
    frontend.
-   Frontend is not a prerequisite for proving ingestion, retrieval, and
    investigation correctness.

## 4. Core domain models

All IDs should be stable UUIDs or another documented opaque ID format.
Timestamps should be timezone-aware UTC. Target environment identifiers
must be explicit.

### Document

-   `id`
-   `source_name`
-   `media_type`
-   `content_hash`
-   `version_label` (nullable)
-   `status`: `pending`, `processing`, `indexed`, `failed`, `archived`
-   `system_scope` (nullable)
-   `environment_scope` (nullable)
-   `created_at`, `updated_at`
-   `source_metadata` JSON

### DocumentChunk

-   `id`
-   `document_id`
-   `content`
-   `chunk_index`
-   `page_number` (nullable)
-   `section_path` (nullable)
-   `heading` (nullable)
-   `content_hash`
-   `embedding` where supported
-   `created_at`

### Investigation

-   `id`
-   `user_id` (nullable for local-only mode)
-   `question`
-   `target_system` (nullable)
-   `target_environment` (nullable)
-   `status`: `queued`, `running`, `waiting_for_approval`, `completed`,
    `insufficient_evidence`, `failed`, `cancelled`
-   `graph_thread_id`
-   `started_at`, `completed_at`
-   `summary` (nullable)

### EvidenceItem

-   `id`
-   `investigation_id`
-   `kind`: `document_passage`, `tool_observation`,
    `historical_episode`, `user_input`
-   `source_id`
-   `source_version` (nullable)
-   `observed_at` (nullable)
-   `target_scope` JSON
-   `content_excerpt` or normalized payload reference
-   `trust_status`: `observed`, `source_backed`, `inferred`,
    `unverified`
-   `metadata` JSON

### Hypothesis

-   `id`
-   `investigation_id`
-   `statement`
-   `status`: `open`, `supported`, `contradicted`, `verified`,
    `rejected`
-   `supporting_evidence_ids`
-   `contradicting_evidence_ids`
-   `verification_notes`

### InvestigationEpisode

-   `id`
-   `investigation_id`
-   `symptom_summary`
-   `target_scope`
-   `diagnostic_steps`
-   `hypotheses_summary`
-   `outcome_summary`
-   `verification_status`: `verified`, `partially_verified`,
    `unverified`, `unresolved`
-   `source_evidence_ids`
-   `created_at`

### AuditEvent

-   `id`
-   `investigation_id`
-   `event_type`
-   `actor_type`
-   `actor_id` (nullable)
-   `timestamp`
-   `status`
-   `safe_metadata` JSON
-   `correlation_id`

Do not store API keys, passwords, access tokens, or unrestricted
secret-bearing command output in these records.

## 5. The three memory types

### 5.1 Working memory

Purpose: state needed to continue one active investigation.

Contains: - question and explicit scope - current plan and graph phase -
retrieved evidence IDs - hypotheses and their status - completed steps
and pending checks - tool-call budget and iteration count - unresolved
user questions

Implementation: - LangGraph typed state. - Persistent checkpoints keyed
by investigation/thread ID. - Store evidence payloads in the database
and refer to them by ID instead of copying large blobs into graph
state. - Bound state size and redact secrets. - A new investigation must
receive a new scope; do not silently inherit another investigation's
server or environment.

### 5.2 Episodic memory

Purpose: recall what happened in prior investigations.

Contains: - symptom and target scope - diagnostic steps and
observations - failed and supported hypotheses - outcome and
verification status - evidence references and timestamps

Retrieval: - filter by relevant system/environment and access scope
first - use keyword and optional vector similarity - show episode date,
target scope, and verification status - label old episodes as
historical, not live facts - do not automatically convert a historical
resolution into a current diagnosis

### 5.3 Semantic memory

Purpose: stable, reusable knowledge from documents and approved
knowledge items.

Contains: - runbooks, manuals, technical documentation - architecture
and dependency facts - source-backed knowledge items - document
versions, validity, and applicability metadata

Retrieval: - hybrid keyword + semantic retrieval - return chunk IDs,
source IDs, version, page/section, and score metadata - apply scope and
access filters before returning results - detect archived or superseded
sources when metadata permits - cite retrieved source records, never
invent citation identifiers

### Separate audit/trace system

Audit is not a fourth memory type. It is a record of what the system
did: - graph transitions - model calls and structured outcomes, subject
to safe logging policy - Goose/MCP calls and statuses - approval
events - failures, retries, and verification outcomes

## 6. Memory manager interface

A small interface is sufficient:

``` python
class MemoryManager:
    async def load_working_state(self, investigation_id: str): ...
    async def save_working_state(self, investigation_id: str, state): ...
    async def retrieve_episodes(self, query, target_scope, limit=5): ...
    async def retrieve_knowledge(self, query, filters, limit=8): ...
    async def save_episode(self, episode): ...
    async def promote_knowledge(self, item, *, provenance, review_status): ...
```

Use typed Pydantic models for arguments and return values. Do not return
unstructured arbitrary dictionaries where a schema is important.

Knowledge promotion must be explicit and provenance-preserving. In the
MVP, only verified or reviewed findings can be promoted. The system
should not learn uncritically from model-generated summaries.

## 7. LangGraph state and workflow

### State fields

-   `investigation_id`
-   `question`
-   `target_scope`
-   `plan`
-   `document_evidence_ids`
-   `episode_evidence_ids`
-   `live_evidence_ids`
-   `hypotheses`
-   `applicability_checks`
-   `missing_information`
-   `iteration_count`
-   `tool_call_count`
-   `status`
-   `report_id` (nullable)

Keep full documents, large tool payloads, and secrets out of the graph
state; store references instead.

### Graph nodes

1.  `initialize`: validate request and scope.
2.  `resolve_context`: retrieve relevant prior episodes and semantic
    knowledge.
3.  `plan_investigation`: produce a bounded plan.
4.  `gather_live_evidence`: call only allowed Goose/MCP tools when
    needed.
5.  `normalize_evidence`: validate schemas and persist observations.
6.  `assess_applicability`: classify prerequisites as `confirmed`,
    `contradicted`, or `unknown`.
7.  `evaluate_evidence`: determine whether sufficient evidence exists or
    more retrieval is required.
8.  `request_approval`: only for any future operation that changes
    state; no write operations in the MVP.
9.  `generate_report`: generate a structured report with source
    references.
10. `finalize`: persist outcome, episode, and audit events.

### Conditional routing

-   If the request is document-only, skip live tool collection.
-   If target scope is missing and necessary, ask a clarifying question
    rather than guessing.
-   If evidence is insufficient, run at most a configured number of
    additional retrieval/diagnostic cycles, then return
    `insufficient_evidence`.
-   If Goose/MCP is unavailable, continue in document-only mode when
    useful and clearly disclose the limitation.
-   Stop when the report is complete, cancelled, or the execution budget
    is exhausted.

### Defaults

Use configuration for maximum iterations, maximum tool calls, maximum
wall time, retrieval limits, and model-call budget. No infinite loops.

## 8. Retrieval and citations

### Chunking

-   Prefer heading/section-aware chunking.
-   Preserve page numbers, headings, source filenames, document IDs, and
    version hashes.
-   Use overlap only when it improves retrieval quality.
-   Keep original text or a controlled reference to it so citations can
    be rendered.

### Hybrid retrieval

1.  Apply access and scope filters.
2.  Run keyword search.
3.  Run vector search if configured.
4.  Merge/rerank candidates.
5.  Return a bounded number of chunks with provenance.
6.  Deduplicate overlapping passages.

### Citation contract

A citation must resolve to a stored document/chunk or evidence record.
Model output should reference evidence IDs selected from the supplied
context. Validate all returned IDs before displaying the report. If a
claim has no supporting source, label it as an inference or unverified
hypothesis.

## 9. Goose/MCP integration contract

Define a Threadline-owned adapter that exposes a small allowlisted set
of operations, for example: - `get_service_status` -
`read_application_logs` - `get_deployment_metadata` -
`check_path_exists` - `get_recent_job_status`

These are example capabilities, not assumptions that every Goose
installation already provides them. Implement them only where the
environment has a supported tool or MCP server.

Requirements: - use the documented Goose interface available in the
target version - validate tool arguments and result schemas - enforce
target-scope allowlists outside the LLM - use read-only permissions in
the MVP - set per-tool timeouts and output-size limits - redact secrets
from results and traces - handle unavailable tools and malformed
responses safely - provide a fake adapter for tests

Do not assume Goose is directly importable into Python. Do not allow
document text or model output to change the tool allowlist.

## 10. API contract (initial proposal)

### Documents

-   `POST /api/v1/documents` --- upload a supported document.
-   `GET /api/v1/documents` --- list documents and ingestion status.
-   `GET /api/v1/documents/{document_id}` --- inspect metadata.
-   `POST /api/v1/documents/{document_id}/reindex` --- reprocess an
    existing document.

### Investigations

-   `POST /api/v1/investigations` --- create an investigation.
-   `GET /api/v1/investigations/{id}` --- inspect status and summary.
-   `GET /api/v1/investigations/{id}/events` --- retrieve progress
    events.
-   `POST /api/v1/investigations/{id}/resume` --- resume a checkpointed
    investigation.
-   `POST /api/v1/investigations/{id}/cancel` --- cancel the workflow.

### Reports and evidence

-   `GET /api/v1/investigations/{id}/report` --- retrieve the report.
-   `GET /api/v1/investigations/{id}/evidence` --- retrieve evidence
    records.

All endpoints require request validation, consistent errors, and
configured access control. Streaming transport (SSE/WebSocket) can be
selected during implementation; polling is acceptable for the first MVP.

## 11. Security and trust boundaries

-   Uploaded documents and tool outputs are untrusted data.
-   Prompt injection inside documents must not change system policy or
    authorize tools.
-   Enforce authorization in code, not only in prompts.
-   Read-only tools only in the MVP.
-   No unrestricted shell execution.
-   No automatic service restarts, writes, or database mutations.
-   Use explicit target allowlists.
-   Apply timeouts and output limits.
-   Keep secrets out of prompts, logs, reports, and memory.
-   Separate user-visible summaries from raw operational payloads.
-   Production mode must fail closed if required authentication or
    security configuration is missing.
-   Keep a clear approval mechanism for any future state-changing
    operation.

## 12. Testing strategy

### Unit tests

-   extraction and chunk metadata
-   retrieval filters and ranking merge
-   citation ID validation
-   memory isolation and retrieval
-   applicability classification
-   tool argument validation
-   report schema validation

### Integration tests

-   upload → index → retrieve → cited answer
-   investigation graph with mocked model and fake Goose adapter
-   checkpoint → interrupt → resume
-   historical episode retrieval with scope mismatch
-   Goose unavailable → document-only fallback
-   audit events persisted for successful and failed calls

### Security tests

-   prompt injection in documents cannot enable tools
-   unapproved tool names are rejected
-   target-scope escape attempts are rejected
-   secrets are redacted
-   users cannot access unauthorized documents or investigations
-   no write-capable operation can run in MVP mode

### Evaluation dataset

Create a small version-controlled dataset with questions, expected
source IDs, target scope, and expected answer attributes. Track
Recall@k, citation validity, applicability accuracy, and abstention when
evidence is insufficient.

## 13. Configuration

Use environment variables and typed settings. Provide `.env.example`
without real secrets.

Suggested settings: - `THREADLINE_ENV` - `DATABASE_URL` -
`MODEL_PROVIDER` - `MODEL_NAME` - provider credential variable(s) -
`EMBEDDING_MODEL` - `GOOSE_ENABLED` - Goose/MCP connection
configuration - `MAX_INVESTIGATION_ITERATIONS` - `MAX_TOOL_CALLS` -
`MAX_INVESTIGATION_SECONDS` - `MAX_RETRIEVAL_RESULTS` - `LOG_LEVEL` -
authentication/security settings

Never commit secrets. Keep provider-specific details behind adapters.

## 14. Implementation sequence

1.  Establish package, settings, health endpoint, database, and tests.
2.  Implement document ingestion with provenance.
3.  Implement keyword retrieval and cited answers.
4.  Add vector retrieval and hybrid ranking behind an interface.
5.  Implement three memory services and checkpointing.
6.  Implement the LangGraph investigation workflow with fake adapters.
7.  Add Goose/MCP integration and read-only tool policies.
8.  Implement applicability checks and structured reports.
9.  Add audit/history endpoints.
10. Build a minimal web UI.
11. Run security and evaluation suites; document limitations.

Do not start with the full UI, autonomous remediation, multiple
autonomous agents, or a graph database. Demonstrate the end-to-end
evidence workflow first.

## 15. Definition of done

The technical MVP is done when: - tests pass without live model
credentials - ingestion preserves source metadata - citations are
validated against stored records - the three memory types are separate
in code and semantics - working state can resume after interruption -
prior incidents are treated as historical evidence - Goose is accessed
through a documented supported interface - read-only tool policies are
enforced outside the model - investigation reports distinguish observed,
inferred, and verified claims - audit records are separate from memory -
setup, security limitations, and evaluation instructions are documented
