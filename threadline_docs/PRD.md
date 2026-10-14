# Threadline --- Product Requirements Document (PRD)

**Status:** Draft v1.0\
**Product:** Threadline\
**Repository:** `threadline` (proposed; availability not verified)\
**Category:** Evidence-driven operational knowledge and investigation
agent\
**Primary integrations:** LangChain, LangGraph, Goose, MCP

## 1. Executive summary

Threadline is an operational knowledge agent that connects internal
documentation with live, approved system observations. It helps users
investigate technical and operational problems by retrieving relevant
manuals, runbooks, and incident reports; gathering current evidence
through Goose and MCP tools; checking whether documented procedures
apply to the target environment; and producing an auditable,
source-backed investigation report.

Threadline is a separate product repository. It must not depend on
ForgeLoop or import ForgeLoop internals. A future integration may use a
stable API or MCP interface, but that is out of scope for the MVP.

Threadline is not merely a conversational RAG chatbot. Its defining
capability is evidence traceability: important conclusions must link to
source documents or recorded tool observations, and the system must
distinguish verified facts, hypotheses, and unresolved questions.

## 2. Problem statement

Operational troubleshooting often requires engineers to search multiple
places: runbooks, manuals, incident history, application logs, service
status, and environment configuration. The information is fragmented,
procedures may be outdated, and a plausible answer can be mistaken for a
confirmed diagnosis.

Threadline reduces this fragmentation by coordinating document retrieval
and live evidence gathering in one investigation workflow. It should
help users answer: - What is known about this issue? - Which sources
support that conclusion? - Does the documented procedure apply to this
environment? - What evidence is missing or contradictory? - What should
be checked next? - Was the proposed resolution actually verified?

## 3. Product goals

1.  Provide source-backed answers from indexed operational documents.
2.  Preserve source provenance, document version, and page/section
    references where available.
3.  Integrate an actual Goose instance through supported interfaces,
    especially MCP, for approved operational evidence gathering.
4.  Orchestrate multi-step investigations with LangGraph.
5.  Implement exactly three functional memory types: working, episodic,
    and semantic.
6.  Keep audit and trace records separate from memory.
7.  Clearly distinguish observed facts, inferred hypotheses,
    recommendations, and verified outcomes.
8.  Start lightweight enough for local development and a single-user
    MVP, while keeping storage and integration boundaries replaceable.
9.  Include automated tests and a repeatable evaluation set for
    retrieval, citations, and investigation quality.

## 4. Non-goals for the MVP

-   Autonomous production remediation.
-   Unrestricted shell or database access.
-   A general-purpose coding agent.
-   Rebuilding Goose or LangChain.
-   A custom foundation model or model training pipeline.
-   A complex multi-agent swarm.
-   A graph database requirement.
-   Automatic promotion of every investigation conclusion into reusable
    knowledge.
-   Direct dependency on ForgeLoop internals.
-   Guaranteed diagnosis when evidence is incomplete.
-   Replacing existing monitoring, incident management, or
    access-control systems.

## 5. Target users and primary use cases

### Primary user

A developer, IT operator, system administrator, or support engineer who
needs to investigate a technical issue using internal documentation and
approved system observations.

### Use case A: Document-backed troubleshooting

A user enters an error message or operational question. Threadline
retrieves relevant runbooks and manuals, summarizes applicable steps,
and cites the source passages.

### Use case B: Live evidence investigation

A user asks Threadline to investigate an issue in a named environment.
Threadline retrieves documentation, calls approved read-only Goose/MCP
tools, compares the observations with documented procedures, and
generates an evidence-backed report.

### Use case C: Reuse a past investigation

Threadline finds a similar previous incident and presents it as
historical evidence, while explicitly checking whether the old
environment and conditions match the current case.

### Use case D: Resume an interrupted investigation

A user resumes an investigation using persisted LangGraph
state/checkpoints without losing the plan, evidence references, or
outstanding questions.

### Use case E: Audit a conclusion

A user opens a report and follows each material finding to its source
document, retrieved passage, or recorded tool observation.

## 6. Product principles

-   **Evidence before confidence:** Do not claim a root cause is
    confirmed without supporting evidence.
-   **Provenance by default:** Store source IDs and references with
    retrieved material and findings.
-   **Least privilege:** Operational tools are allowlisted and read-only
    by default.
-   **Explicit uncertainty:** Mark hypotheses and unknowns instead of
    inventing missing facts.
-   **Bounded execution:** Limit workflow iterations, tool calls,
    elapsed time, and context size.
-   **Human control:** Any state-changing operation requires explicit
    authorization and is excluded from the MVP.
-   **Memory separation:** Working, episodic, and semantic memory have
    distinct purposes and retention rules.
-   **Reproducibility:** Record enough trace information to understand
    and evaluate a run.
-   **Replaceable components:** Keep provider, storage, retriever, and
    Goose interfaces behind adapters.
-   **Independent repository:** Threadline can be installed, tested, and
    run without ForgeLoop.

## 7. MVP scope

### Included

1.  FastAPI backend.
2.  Document upload and ingestion for PDF, DOCX, Markdown, and TXT.
3.  Document metadata and version/hash tracking.
4.  Hybrid retrieval using keyword/full-text search and vector
    similarity, with a simple retrieval interface.
5.  Chat/investigation endpoint with streamed or polling progress.
6.  LangGraph investigation workflow.
7.  LangChain retrieval and structured model output.
8.  Goose integration through a supported external interface and
    approved MCP tools.
9.  Read-only operational evidence collection.
10. Three memory types:
    -   Working memory: current investigation state and checkpoint.
    -   Episodic memory: previous investigation records and outcomes.
    -   Semantic memory: documents and reusable, source-backed
        knowledge.
11. Separate audit and tool trace records.
12. Evidence-backed investigation report.
13. Basic web UI for documents, investigation sessions, evidence, and
    reports.
14. Authentication appropriate for local/dev deployment; production auth
    is configurable and must not be bypassed in production mode.
15. Automated unit/integration tests and a small evaluation dataset.
16. Docker Compose development setup.

### Deferred

-   Multi-tenant enterprise permissions beyond a basic ownership/access
    model.
-   SSO and enterprise identity providers.
-   Automated remediation and write-capable MCP tools.
-   Complex document OCR pipelines for scanned PDFs.
-   Dedicated graph database.
-   Distributed job queue and multi-node deployments.
-   Advanced memory consolidation agents.
-   Agent-to-agent collaboration beyond the primary coordinator and
    integrations.

## 8. Functional requirements

### FR-01: Document ingestion

The user can upload supported files. The system extracts text, records
document metadata, computes a content hash, splits content into
retrieval chunks, and indexes the chunks. Ingestion failures must be
visible and must not leave a document marked as successfully indexed.

### FR-02: Source provenance

Every indexed chunk must retain a document ID, version/hash, source
filename, and available page/section/heading information. Every answer
citation must resolve to a stored source reference.

### FR-03: Retrieval

The system supports keyword search and semantic search. Retrieval must
allow filters for document type, system/environment, and document
status/version when those metadata exist. Hybrid scoring can initially
be a simple configurable weighted combination or reciprocal-rank fusion.

### FR-04: Investigation orchestration

LangGraph coordinates the investigation state, retrieval, optional live
evidence gathering, applicability checks, and report generation. It must
have bounded retries and a terminal outcome for insufficient evidence.

### FR-05: Goose/MCP evidence gathering

Threadline connects to a configured Goose deployment through a
documented supported interface. Operational capabilities are exposed as
allowlisted MCP tools. The MVP uses read-only tools only. Tool results
are normalized and recorded with timestamp, tool name, target scope, and
execution status.

### FR-06: Applicability verification

Threadline compares the procedure's prerequisites and applicability
metadata with known target-environment facts. It classifies each
important prerequisite as confirmed, contradicted, or unknown. Unknown
must not be silently treated as confirmed.

### FR-07: Investigation report

Each report includes: - Request and target scope. - Executive summary. -
Observed facts and their sources. - Relevant documents/procedures. -
Hypotheses and supporting/contradicting evidence. - Applicability
checklist. - Recommended next steps. - Risks and required approvals. -
Missing evidence and uncertainty. - Run ID and timestamps.

### FR-08: Working memory

Current investigation state is checkpointed and can be resumed. Working
memory must be scoped to a thread/investigation and must not leak
evidence between unrelated environments or users.

### FR-09: Episodic memory

Completed investigations are stored as structured episodes. Episodes
include symptoms, scope, evidence references, actions attempted,
outcome, and verification status. Retrieval of a past episode must
display its age and scope and must not imply that a previous resolution
is automatically applicable.

### FR-10: Semantic memory

Documents and approved reusable knowledge are indexed independently of
individual conversation state. Reusable knowledge must retain provenance
and version information.

### FR-11: Audit and trace

Audit/trace records are stored separately from the three memory types.
Record workflow transitions, model calls at a suitable metadata level,
tool calls, approval events, errors, and verification results. Avoid
storing secrets or unnecessary sensitive payloads.

### FR-12: Access and safety

The application must enforce configured access boundaries for documents,
investigations, and tools. Prompt-injected instructions found in
documents or tool outputs are untrusted data and must not override
system policies. No arbitrary command execution is enabled by default.

### FR-13: Evaluation

The project includes repeatable tests for retrieval relevance, citation
correctness, scope isolation, applicability classification, tool policy
enforcement, and report completeness.

## 9. Non-functional requirements

-   Local development should work with Docker Compose and documented
    environment variables.
-   The core application must have automated tests that run without live
    model credentials by using mock adapters.
-   External provider and Goose failures must return controlled,
    actionable errors.
-   Every investigation has configurable limits for duration, model
    calls, and tool calls.
-   Logs must use run IDs and avoid exposing secrets.
-   Ingestion and retrieval must be deterministic where practical.
-   Database migrations must be version-controlled.
-   The API must validate inputs and use explicit response schemas.
-   The application must document that generated recommendations are not
    proof of a diagnosis.

## 10. Success metrics

Initial engineering targets, to be validated against a test corpus: -
100% of displayed citations resolve to an existing source record. - 0
unapproved state-changing tool calls in the test suite. - 100% of
investigations have a terminal status or a resumable checkpoint. - At
least 80% Recall@5 on the curated retrieval evaluation set after
baseline tuning. - At least 90% pass rate on scope-isolation and
tool-policy tests. - Reports label unresolved hypotheses as
unverified. - The entire test suite can run without live API
credentials.

These are targets, not claims of achieved performance.

## 11. User experience

Primary screens: 1. **Knowledge Library:** upload files, inspect
metadata, view ingestion status and document versions. 2.
**Investigation Workspace:** enter a question, select a target
environment, watch workflow progress, and view evidence. 3.
**Investigation Report:** review findings, source citations,
applicability, uncertainty, and recommendations. 4. **History and
Audit:** reopen previous investigations and inspect traceable events.

## 12. Release acceptance criteria

The MVP is acceptable when a user can: 1. Upload a runbook and a sample
incident report. 2. Ask a question and receive an answer with valid
source references. 3. Start a live investigation using configured
read-only Goose/MCP tools. 4. See which facts came from documents and
which came from live tools. 5. See confirmed, contradicted, and unknown
applicability checks. 6. Resume an interrupted investigation. 7. View a
past investigation without confusing it with current live evidence. 8.
Inspect an audit trail for the run. 9. Run the automated test suite
without live credentials. 10. Run the application using documented local
setup instructions.

## 13. Risks and mitigations

-   **Stale documentation:** track versions and dates; surface stale or
    unknown freshness.
-   **Incorrect retrieval:** use hybrid search and a curated evaluation
    corpus.
-   **Hallucinated citations:** citations must be created from retrieval
    records, not generated as arbitrary strings.
-   **Tool output prompt injection:** treat tool output as untrusted
    data; tool permissions remain enforced outside the LLM.
-   **False diagnosis:** separate observations, hypotheses, and verified
    conclusions.
-   **Memory contamination:** scope memory by investigation, user, and
    target environment.
-   **Overengineering:** begin with one coordinator and deterministic
    helper functions; defer agent swarms and graph databases.
-   **Goose integration drift:** use documented interfaces and
    integration tests against the configured version.

## 14. Open decisions

Resolve these during implementation without blocking the initial
architecture: - Exact Goose invocation/connection mode supported by the
installed Goose version. - Default model provider and embedding model. -
Whether vector search uses pgvector immediately or a local adapter for
the first local-only prototype. - Production authentication provider. -
Document retention and deletion policy. - Deployment target and
operational monitoring requirements.
