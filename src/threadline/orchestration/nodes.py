"""M6 investigation nodes using bounded LangGraph routing."""

from __future__ import annotations

from datetime import UTC, datetime

from threadline.memory.manager import MemoryManager
from threadline.orchestration.state import InvestigationState
from threadline.redact import redact_secrets

MAX_EXTRA_RETRIEVAL_PASSES = 1


def initialize(state: InvestigationState, settings: Any) -> dict[str, Any]:
    question = redact_secrets(str(state.get("question", "") or "").strip())
    target_system = state.get("target_system") or state.get("target_scope", {}).get("system")
    target_environment = state.get("target_environment") or state.get("target_scope", {}).get("environment")
    missing = []
    if not question:
        missing.append("question")
    if not target_system:
        missing.append("target_system")
    if not target_environment:
        missing.append("target_environment")
    status = "running" if not missing else "failed"
    return {
        "question": question,
        "target_system": target_system,
        "target_environment": target_environment,
        "iteration_count": 0,
        "tool_call_count": 0,
        "plan": [],
        "retrieved_document_ids": [],
        "retrieved_chunks": [],
        "episode_ids": [],
        "live_evidence": [],
        "missing_information": missing,
        "limitations": [],
        "report": None,
        "status": status,
        "max_iterations": int(settings.get("max_iterations", 5) if hasattr(settings, "get") else getattr(settings, "max_investigation_iterations", 5)),
        "max_tool_calls": int(settings.get("max_tool_calls", 10) if hasattr(settings, "get") else getattr(settings, "max_tool_calls", 10)),
    }


def resolve_context(
    state: InvestigationState,
    memory_manager: MemoryManager,
) -> dict[str, Any]:
    investigation_id = state.get("investigation_id", "")
    target_scope = {
        "target_system": state.get("target_system"),
        "target_environment": state.get("target_environment"),
    }
    episodes = memory_manager.retrieve_episodes(
        state.get("question", ""),
        target_scope=target_scope,
        limit=5,
    )
    working = memory_manager.load_working_state(investigation_id)
    evidence = list(working.evidence_ids) if working is not None else []
    plan = list(working.plan) if working is not None else []
    return {
        "episode_ids": [episode.episode.id for episode in episodes if getattr(episode.episode, "id", None)],
        "retrieved_document_ids": evidence if evidence else [],
        "plan": plan,
    }


def plan_investigation(state: InvestigationState, memory_manager: MemoryManager | None = None) -> dict[str, Any]:
    question = state.get("question", "")
    target = state.get("target_system", "target")
    plan = [
        f"Retrieve operational documentation relevant to {question}.",
        f"Compare documented procedure with {target} observations where allowed.",
        "Identify missing or contradictory evidence before concluding.",
    ]
    if memory_manager is not None:
            memory_manager.save_working_state(
                state["investigation_id"],
                {
                    "question": question,
                    "target_system": state.get("target_system"),
                    "target_environment": state.get("target_environment"),
                    "plan": plan,
                    "iteration_count": state.get("iteration_count", 0),
                    "tool_call_count": state.get("tool_call_count", 0),
                    "status": "running",
                },
            )
    return {"plan": plan, "iteration_count": (state.get("iteration_count", 0) + 1)}


def retrieve_documents(state: InvestigationState, retrieval_func, query: str | None = None) -> dict[str, Any]:
    search_query = query or state.get("question", "")
    filters = None
    results = []
    try:
        results = retrieval_func(search_query, None, 8) if callable(retrieval_func) else []
    except Exception:
        results = []
    ids: list[str] = []
    chunks: list[dict[str, Any]] = []
    for item in results or []:
        if isinstance(item, dict):
            identifier = item.get("chunk_id", item.get("id"))
            content = item.get("content", "")
        else:
            identifier = getattr(item, "id", None) or getattr(item, "chunk_id", None)
            content = getattr(item, "content", "")
        if identifier is not None:
            key = str(identifier)
            ids.append(key)
            chunks.append({"chunk_id": key, "content": content})
    # De-duplicate IDs while preserving order.
    unique_ids: list[str] = []
    for item in ids:
        if item not in unique_ids:
            unique_ids.append(item)
    return {
        "retrieved_document_ids": unique_ids,
        "retrieved_chunks": chunks,
        "tool_call_count": state.get("tool_call_count", 0) + len(ids),
    }


def gather_live_evidence(
    state: InvestigationState,
    goose_adapter: Any,
    policy: Any,
    target_system: str,
    target_environment: str,
) -> dict[str, Any]:
    if not goose_adapter or state.get("mode") == "document_only":
        return {
            "limitations": list(state.get("limitations", [])) + ["Live evidence gathering disabled; document-only mode."],
        }
    current_iteration = (state.get("iteration_count", 0) + 1 if state.get("iteration_count", 0) < 1 else state.get("iteration_count", 0))
    tool_name = "get_service_status"
    try:
        if policy is not None:
            policy.validate(tool_name, target_system, target_environment)
        observation = goose_adapter.invoke(
            tool_name,
            target_system=target_system,
            target_environment=target_environment,
        )
    except Exception as exc:
        limitation = redact_secrets(str(exc))
        return {"limitations": list(state.get("limitations", [])) + [limitation]}
    evidence = list(state.get("live_evidence", []))
    evidence.append(observation)
    return {
        "live_evidence": evidence,
        "tool_call_count": state.get("tool_call_count", 0) + 1,
    }


def normalize_evidence(state: InvestigationState) -> dict[str, Any]:
    normalized = []
    for item in state.get("live_evidence", []):
        normalized.append(
            {
                "kind": "tool_observation",
                "source_id": item.get("tool_name"),
                "adapter": item.get("adapter"),
                "target_scope": {
                    "system": item.get("target_system"),
                    "environment": item.get("target_environment"),
                },
                "content_excerpt": str(item.get("result", {}))[:500],
                "trust_status": "observed",
            }
        )
    missing = list(state.get("missing_information", []))
    if not state.get("retrieved_document_ids") and not normalized:
        missing.append("No relevant document passages retrieved.")
    return {"missing_information": missing}


def evaluate_evidence(state: InvestigationState) -> tuple[dict[str, Any], str]:
    has_docs = bool(state.get("retrieved_document_ids"))
    has_live = bool(state.get("live_evidence"))
    if state.get("status") == "failed":
        return ({"status": "failed"}, "generate_report")
    if has_docs or has_live:
        return ({"status": "running"}, "generate_report")
    iteration = state.get("iteration_count", 0)
    max_iterations = int(state.get("max_iterations", 3))
    if iteration < min(max_iterations, 2):
        return ({"iteration_count": iteration + 1, "status": "running"}, "retrieve_more")
    return ({"status": "insufficient_evidence"}, "generate_report")


def assess_applicability(state: InvestigationState) -> dict[str, Any]:
    target_system = state.get("target_system")
    target_environment = state.get("target_environment")
    checks: list[dict[str, Any]] = []
    if target_system and target_environment:
        checks.append(
            {
                "id": "target_scope",
                "prerequisite": "Investigation target scope is supplied",
                "status": "confirmed",
                "evidence_ids": [],
                "details": f"{target_system}/{target_environment}",
            }
        )
    else:
        checks.append(
            {
                "id": "target_scope",
                "prerequisite": "Investigation target scope is supplied",
                "status": "unknown",
                "evidence_ids": [],
                "details": "Target system or environment is missing.",
            }
        )

    retrieved_chunks = state.get("retrieved_chunks", [])
    matching_document_ids = []
    conflicting_document_ids = []
    for chunk in retrieved_chunks:
        scope = chunk.get("metadata", {}) or {}
        chunk_system = scope.get("target_system") or scope.get("system_scope")
        chunk_environment = scope.get("target_environment") or scope.get("environment_scope")
        doc_id = chunk.get("document_id")
        if not target_system or not target_environment:
            continue
        if chunk_system and chunk_environment:
            if chunk_system == target_system and chunk_environment == target_environment:
                if doc_id and doc_id not in matching_document_ids:
                    matching_document_ids.append(doc_id)
            else:
                if doc_id and doc_id not in conflicting_document_ids:
                    conflicting_document_ids.append(doc_id)
    if retrieved_chunks:
        if conflicting_document_ids and not matching_document_ids:
            status = "contradicted"
        elif matching_document_ids:
            status = "confirmed"
        else:
            status = "unknown"
        checks.append(
            {
                "id": "document_scope_match",
                "prerequisite": "Retrieved documentation applies to the target scope",
                "status": status,
                "evidence_ids": matching_document_ids or conflicting_document_ids or state.get("retrieved_document_ids", []),
                "details": "Documentation scope matches the target." if status == "confirmed" else "Documentation scope does not clearly match the target.",
            }
        )

    live_evidence = state.get("live_evidence", [])
    if live_evidence:
        observed_ids = [str(item.get("result", {}).get("target_system")) for item in live_evidence]
        if target_system and all(item.get("target_system") == target_system and item.get("target_environment") == target_environment for item in live_evidence):
            status = "confirmed"
        elif target_system and any(item.get("target_system") != target_system or item.get("target_environment") != target_environment for item in live_evidence):
            status = "contradicted"
        else:
            status = "unknown"
        checks.append(
            {
                "id": "live_evidence_scope_match",
                "prerequisite": "Observed Goose/MCP facts apply to the requested target",
                "status": status,
                "evidence_ids": [], 
                "details": "Observed live evidence was gathered in the requested scope.",
                "observed_targets": observed_ids,
            }
        )
    else:
        checks.append(
            {
                "id": "live_evidence_scope_match",
                "prerequisite": "Observed Goose/MCP facts apply to the requested target",
                "status": "unknown",
                "evidence_ids": [],
                "details": "No live operational evidence is available.",
            }
        )
    checks.append(
        {
            "id": "unknown_requires_confirmation",
            "prerequisite": "Unknown prerequisites are not treated as confirmed",
            "status": "confirmed",
            "evidence_ids": [],
            "details": "Any check marked unknown must remain unverified.",
        }
    )
    return {"applicability_checks": checks}


def generate_report(state: InvestigationState) -> dict[str, Any]:
    question = state.get("question", "")
    live = state.get("live_evidence", [])
    facts = []
    for item in live:
        facts.append(
            {
                "source": item.get("tool_name"),
                "reference": item.get("adapter"),
                "excerpt": str(item.get("result", {}))[:300],
                "trust_status": "observed",
            }
        )
    doc_references = state.get("retrieved_document_ids", [])
    applicability_checks = state.get("applicability_checks", [])
    uncertain = [check for check in applicability_checks if check.get("status") == "unknown"]
    observed_facts = facts + [
        {
            "source": "documentation",
            "reference": doc_id,
            "excerpt": "Retrieved document reference",
            "trust_status": "retrieved",
        }
        for doc_id in doc_references
    ]
    report = {
        "request": question,
        "target_scope": {
            "system": state.get("target_system"),
            "environment": state.get("target_environment"),
        },
        "executive_summary": (
            "Evidence-backed investigation completed using documentation and configured read-only Goose observations."
            if (doc_references or live)
            else "Insufficient evidence is available to draw a conclusion."
        ),
        "summary": (
            "Evidence-backed investigation completed using documentation and configured read-only Goose observations."
            if (doc_references or live)
            else "Insufficient evidence is available to draw a conclusion."
        ),
        "observed_facts": observed_facts,
        "document_references": doc_references,
        "hypotheses": [{"statement": item, "status": "open"} for item in state.get("plan", [])],
        "applicability_checks": applicability_checks,
        "recommended_next_steps": [
            "Inspect each referenced document passage.",
            "Verify observations in the target environment.",
        ],
        "risks_and_required_approvals": [
            "No state-changing actions were requested or executed.",
            "Human approval is required for any remediation or configuration change.",
        ],
        "missing_evidence": state.get("missing_information", []),
        "uncertainty": [item.get("details") for item in uncertain] or state.get("missing_information", []),
        "limitations": state.get("limitations", []),
        "run_id": state.get("investigation_id"),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    return {"report": report, "status": "completed" if (doc_references or live) else "insufficient_evidence"}


def finalize(state: InvestigationState, memory_manager: MemoryManager | None = None, audit_manager: Any = None) -> dict[str, Any]:
    if memory_manager is not None:
        try:
            from threadline.memory.models import InvestigationEpisode, TargetScope

            memory_manager.save_episode(
                InvestigationEpisode(
                    investigation_id=state["investigation_id"],
                    symptom_summary=state.get("question", ""),
                    target_scope=TargetScope(
                        target_system=state.get("target_system"),
                        target_environment=state.get("target_environment"),
                    ),
                    diagnostic_steps=state.get("plan", []),
                    hypotheses_summary=state.get("plan", []),
                    outcome_summary=state.get("report", {}).get("summary", "") if state.get("report") else "",
                    verification_status="unverified",
                    source_evidence_ids=state.get("retrieved_document_ids", []),
                )
            )
        except Exception:
            pass
        try:
            memory_manager.save_working_state(
                state["investigation_id"],
                {
                    "question": state.get("question", ""),
                    "target_system": state.get("target_system"),
                    "target_environment": state.get("target_environment"),
                    "evidence_ids": state.get("retrieved_document_ids", []),
                    "iteration_count": state.get("iteration_count", 0),
                    "tool_call_count": state.get("tool_call_count", 0),
                    "status": state.get("status", "completed"),
                },
            )
        except Exception:
            pass
    if audit_manager is not None:
        try:
            audit_manager.record(
                state.get("investigation_id"),
                "investigation.finalized",
                status=state.get("status", "completed"),
                safe_metadata={
                    "summary": state.get("report", {}).get("summary") if state.get("report") else None,
                    "iteration_count": state.get("iteration_count", 0),
                    "tool_call_count": state.get("tool_call_count", 0),
                    "document_ids": state.get("retrieved_document_ids", []),
                },
                correlation_id=state.get("investigation_id"),
            )
        except Exception:
            pass
    return {"status": state.get("status", "completed")}

def route_after_evaluation(state: InvestigationState) -> str:
    if state.get("status") == "failed":
        return "generate_report"
    if state.get("retrieved_document_ids") or state.get("live_evidence"):
        return "generate_report"
    if state.get("iteration_count", 0) < min(int(state.get("max_iterations", 3)), 2):
        return "retrieve_more"
    return "generate_report"
