# Threadline --- Implementation Prompt for an AI Coding Agent

You are implementing **Threadline**, a new, independent repository for
an evidence-driven operational knowledge and investigation agent.

## Mission

Build a working application that combines: - **LangChain** for
model/retrieval integrations and structured outputs. - **LangGraph** for
bounded, resumable investigation workflows. - **The actual Goose
application** through its documented supported interface, preferably MCP
where supported, to gather approved operational evidence. - **Three and
only three functional memory types:** working, episodic, and semantic. -
A separate audit/trace subsystem that is not treated as a fourth memory
type. - A FastAPI backend and a minimal web UI when the core workflow is
stable.

Threadline is separate from the user's existing ForgeLoop repository. Do
not import ForgeLoop modules, assume ForgeLoop APIs, edit ForgeLoop
files, or make Threadline depend on ForgeLoop. A future integration may
be proposed through a stable API/MCP boundary, but it is not part of the
MVP.

## First actions --- inspect before editing

1.  Inspect the repository and existing files before making changes.
2.  Identify existing language, package manager, conventions, tests, and
    current implementation status.
3.  If this repository already contains a plan or implementation, treat
    it as the baseline and extend it rather than replacing it.
4.  Report missing assumptions and risks. Do not invent files, Goose
    APIs, MCP tool names, or successful test results.
5.  Propose a concise implementation plan, then implement in small,
    testable increments. If operating autonomously, proceed with safe,
    reversible steps and stop for clarification when an essential
    decision cannot be grounded.

## Architecture requirements

-   Use Python and FastAPI for the backend.
-   Use LangGraph for the investigation state machine, checkpoints,
    conditional routing, bounded loops, and resumability.
-   Use LangChain where it provides real value for model integration,
    retrieval, document processing, and structured output. Avoid
    wrapping every function in an agent.
-   Integrate Goose as an external application through a documented
    supported interface. Do not assume it is a Python library. Keep it
    behind an adapter.
-   Use MCP tools only when actually available/configured. Build a fake
    Goose/MCP adapter for automated tests.
-   Prefer PostgreSQL + pgvector for a shared web deployment. For a
    deliberately local-only MVP, SQLite + FTS5 is acceptable; semantic
    vector search must remain an explicit optional capability or use a
    replaceable vector adapter. Do not claim FTS5 is semantic search.
-   Keep provider, storage, retriever, and Goose integrations behind
    small interfaces.
-   Provide a minimal Next.js/TypeScript UI after the backend's core
    workflow works; the API and tests must not depend on the UI.

## Exactly three memory types

### 1. Working memory

The current investigation state: question, target scope, plan,
hypotheses, evidence IDs, completed/pending checks, counters, and
status. Use typed LangGraph state and persistent checkpoints. Keep large
payloads and secrets out of graph state; store evidence in persistence
and reference it by ID. Prevent cross-investigation and
cross-environment leakage.

### 2. Episodic memory

Prior investigation records: symptoms, target scope, diagnostic steps,
failed/supported hypotheses, evidence references, outcome, and
verification status. Retrieve relevant episodes with scope filters.
Label episodes as historical, preserve timestamps, and never treat a
past resolution as current live evidence automatically.

### 3. Semantic memory

Reusable knowledge: indexed manuals, runbooks, architecture docs,
source-backed facts, document chunks, and applicability/version
metadata. Use hybrid keyword + vector retrieval when configured. Every
chunk must preserve source, version/hash, and page/section metadata when
available.

Audit/trace records are separate operational records, not a fourth
memory type. Keep tool calls, workflow events, approvals, errors, and
verification results out of automatic model memory injection unless
explicitly selected as relevant evidence.

Implement a `MemoryManager` with typed methods for loading/saving
working state, retrieving episodes, retrieving semantic knowledge,
saving episodes, and promoting reviewed knowledge. Do not build an
autonomous memory-consolidation agent for the MVP. Knowledge promotion
must be explicit and preserve provenance.

## Investigation workflow

Implement a bounded LangGraph flow with nodes or equivalent clearly
separated functions: 1. Validate request and target scope. 2. Resolve
context from episodic and semantic memory. 3. Plan the investigation. 4.
Retrieve relevant documentation. 5. Optionally gather live evidence
through approved Goose/MCP read-only tools. 6. Normalize and persist
evidence. 7. Check procedure applicability using `confirmed`,
`contradicted`, or `unknown`. 8. Evaluate evidence sufficiency. 9.
Perform a limited additional retrieval/diagnostic pass when justified.
10. Generate a structured report with validated citations. 11. Persist
the investigation episode and audit events.

If scope is missing and required, ask a question instead of guessing. If
Goose/MCP is unavailable, continue in document-only mode when useful and
disclose that limitation. If evidence is insufficient after configured
limits, return an explicit insufficient-evidence outcome. No infinite
loops.

## Report requirements

Each investigation report must include: - request and target scope -
summary - observed facts and evidence references - relevant source
documents and versions - hypotheses with supporting and contradicting
evidence - applicability checks - recommended next steps - risks and
approvals - missing evidence and uncertainty - run ID and timestamps

A citation must resolve to a stored document chunk or evidence record.
Never let the model invent arbitrary citation IDs. Clearly distinguish
`observed`, `inferred`, `unverified`, and `verified` claims.

## Safety requirements

-   The MVP is read-only.
-   Do not implement autonomous remediation, service restarts, database
    mutations, or arbitrary shell execution.
-   Define an explicit allowlist of tools and target scopes.
-   Enforce permissions in code, not only in prompts.
-   Treat uploaded documents and tool outputs as untrusted data. Prompt
    injection must not override policy or grant tools.
-   Add tool timeouts, output limits, bounded iteration/tool-call
    budgets, and secret redaction.
-   Production mode must fail closed if required security configuration
    is missing.
-   Never commit credentials or include secrets in tests, logs, reports,
    or memory.

## Testing requirements

Use pytest. Tests must run without live model credentials or a running
Goose instance by using fake adapters. Include tests for: - document
ingestion and source metadata - retrieval filters and citation
validation - memory separation and target-scope isolation - checkpoint
and resume behavior - past episodes marked as historical - unknown
applicability not being treated as confirmed - Goose/MCP unavailable
fallback - unapproved tools rejected - prompt injection cannot change
tool permissions - secrets redacted from traces - insufficient evidence
leads to an explicit outcome - report claims/citations use valid
evidence IDs

Add a small version-controlled evaluation set for retrieval and report
quality. Do not claim a metric has been achieved unless the evaluation
has actually run.

## Engineering workflow

-   Make small, coherent changes.
-   Run the relevant tests after each milestone.
-   Inspect diffs for accidental scope expansion.
-   Keep types, schemas, error handling, and logging explicit.
-   Use migrations for persistent schema changes.
-   Document setup, configuration, architecture, security boundaries,
    and known limitations.
-   Update README and docs to match the implementation, not the other
    way around.
-   Do not add unnecessary dependencies or introduce multi-agent
    complexity without a tested need.
-   Do not claim tests passed unless you executed them and observed the
    result.

## Milestones

M1. Repository skeleton, configuration, health endpoint, test setup, and
storage. M2. Document ingestion with provenance. M3. Keyword search and
citation-backed answers. M4. Semantic/vector retrieval behind a
replaceable interface and hybrid ranking. M5. Three memory types plus
LangGraph checkpointing. M6. Bounded investigation workflow with fake
Goose adapter. M7. Actual Goose/MCP integration using verified supported
interfaces and read-only tools. M8. Applicability checks, structured
report, and separate audit history. M9. Minimal web UI. M10. Security
and evaluation pass; documentation and reproducible local setup.

## Final response expected from the implementer

At the end, report: 1. What was implemented. 2. Key architectural
decisions. 3. Files changed. 4. Tests actually run and their results. 5.
What remains incomplete. 6. Any assumptions about Goose/MCP or model
providers that need user confirmation.

Start by inspecting the repository. Do not blindly generate the entire
application in one unverified pass.
