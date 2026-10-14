"""M6/M8 investigation nodes: bounded routing, evidence collection, applicability, and reporting."""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from typing import Any

from threadline.audit import record_event
from threadline.evidence.citations import validate_report_citations
from threadline.evidence.models import (
    ApplicabilityCheck,
    DocumentReference,
    InvestigationReport,
    ObservedFact,
    ReportScope,
)
from threadline.evidence.verifier import document_key, is_simulated, verify_applicability
from threadline.memory.manager import MemoryManager
from threadline.orchestration.state import InvestigationState
from threadline.redact import redact_secrets

MAX_EXTRA_RETRIEVAL_PASSES = 1

logger = logging.getLogger(__name__)


def _as_mapping(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return dict(vars(item))


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


def retrieve_documents(
    state: InvestigationState,
    retrieval_func,
    query: str | None = None,
    audit_manager: Any = None,
) -> dict[str, Any]:
    search_query = query or state.get("question", "")
    try:
        results = retrieval_func(search_query, None, 8) if callable(retrieval_func) else []
    except Exception as exc:
        reason = redact_secrets(str(exc))[:300]
        record_event(audit_manager, state.get("investigation_id"), "retrieval.failed", status="failed", error=reason)
        return {
            "retrieved_document_ids": [],
            "retrieved_chunks": [],
            "limitations": list(state.get("limitations", [])) + ["Document retrieval failed; no document evidence is available."],
        }

    chunks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in results or []:
        mapping = _as_mapping(item)
        chunk_id = mapping.get("chunk_id") or mapping.get("id")
        if chunk_id is None or str(chunk_id) in seen:
            continue
        key = str(chunk_id)
        seen.add(key)
        meta = mapping.get("metadata") or {}
        chunks.append(
            {
                "chunk_id": key,
                "content": mapping.get("content", ""),
                "document_id": meta.get("document_id"),
                "source_name": mapping.get("source_id"),
                "version": mapping.get("version"),
                "system_scope": meta.get("system_scope"),
                "environment_scope": meta.get("environment_scope"),
                "page_number": meta.get("page_number"),
                "section_path": meta.get("section_path"),
                "heading": meta.get("heading"),
            }
        )
    return {
        "retrieved_document_ids": [chunk["chunk_id"] for chunk in chunks],
        "retrieved_chunks": chunks,
    }


def gather_live_evidence(
    state: InvestigationState,
    goose_adapter: Any,
    policy: Any,
    target_system: str,
    target_environment: str,
    audit_manager: Any = None,
) -> dict[str, Any]:
    investigation_id = state.get("investigation_id")
    if not goose_adapter or state.get("mode") == "document_only":
        return {
            "limitations": list(state.get("limitations", [])) + ["Live evidence gathering disabled; document-only mode."],
        }
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
        reason = redact_secrets(str(exc))
        record_event(
            audit_manager,
            investigation_id,
            "tool.failed",
            status="failed",
            tool_name=tool_name,
            target_system=target_system,
            target_environment=target_environment,
            error=reason[:300],
        )
        return {"limitations": list(state.get("limitations", [])) + [reason]}

    observation = {**observation, "evidence_id": f"obs-{uuid.uuid4().hex[:12]}"}
    record_event(
        audit_manager,
        investigation_id,
        "tool.invoked",
        tool_name=tool_name,
        adapter=observation.get("adapter"),
        target_system=target_system,
        target_environment=target_environment,
        simulated=is_simulated(observation),
    )
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


def assess_applicability(state: InvestigationState, audit_manager: Any = None) -> dict[str, Any]:
    checks = verify_applicability(
        target_system=state.get("target_system"),
        target_environment=state.get("target_environment"),
        documents=state.get("retrieved_chunks", []),
        observations=state.get("live_evidence", []),
    )
    counts = Counter(check.status for check in checks)
    record_event(
        audit_manager,
        state.get("investigation_id"),
        "applicability.assessed",
        counts={status: counts.get(status, 0) for status in ("confirmed", "contradicted", "unknown")},
    )
    return {"applicability_checks": [check.model_dump(mode="json") for check in checks]}


def _recommended_next_steps(
    checks: list[ApplicabilityCheck],
    has_documents: bool,
    has_real_observation: bool,
) -> list[str]:
    steps: list[str] = []
    for check in checks:
        if check.status == "contradicted":
            steps.append(f"Do not apply until reconciled: {check.prerequisite}. {check.details}")
        elif check.status == "unknown" and check.id.startswith("document:"):
            steps.append(f"Confirm scope or add system/environment metadata: {check.prerequisite}.")
    if not has_documents:
        steps.append("Index runbooks or manuals for this system and environment, then re-run the investigation.")
    if not has_real_observation:
        steps.append("Enable a configured read-only Goose/MCP connection to collect observations from the target.")
    if has_documents:
        steps.append("Inspect each referenced document passage.")
    steps.append("Verify observations in the target environment before acting.")
    return list(dict.fromkeys(steps))


def generate_report(state: InvestigationState) -> dict[str, Any]:
    investigation_id = state.get("investigation_id", "")
    chunks = state.get("retrieved_chunks", [])
    observations = state.get("live_evidence", [])
    checks = [ApplicabilityCheck(**item) for item in state.get("applicability_checks", [])]
    check_by_id = {check.id: check for check in checks}

    document_refs = []
    for chunk in chunks:
        check = check_by_id.get(f"document:{document_key(chunk)}")
        document_refs.append(
            DocumentReference(
                chunk_id=chunk["chunk_id"],
                document_id=chunk.get("document_id"),
                source_name=chunk.get("source_name"),
                version=chunk.get("version"),
                page_number=chunk.get("page_number"),
                section_path=chunk.get("section_path"),
                heading=chunk.get("heading"),
                excerpt=str(chunk.get("content", ""))[:300],
                applicability_status=check.status if check else "unknown",
            )
        )

    facts = []
    for observation in observations:
        simulated = is_simulated(observation)
        facts.append(
            ObservedFact(
                evidence_id=str(observation.get("evidence_id", "")),
                source=f"{observation.get('tool_name')} ({observation.get('adapter')})",
                excerpt=redact_secrets(str(observation.get("result", {})))[:300],
                trust_status="unverified" if simulated else "observed",
                simulated=simulated,
                observed_at=observation.get("observed_at"),
            )
        )

    real_count = sum(1 for fact in facts if not fact.simulated)
    simulated_count = len(facts) - real_count
    document_count = len({document_key(chunk) for chunk in chunks})
    status_counts = Counter(check.status for check in checks)

    summary_parts: list[str] = []
    if chunks:
        summary_parts.append(f"{document_count} document(s) returned {len(chunks)} relevant passage(s).")
    if real_count:
        summary_parts.append(f"{real_count} live observation(s) were gathered from the target.")
    if simulated_count:
        summary_parts.append(
            f"{simulated_count} simulated result(s) from the fake Goose adapter were recorded; "
            "they are not observations of the target."
        )
    if not summary_parts:
        summary_parts.append("No documentation or live evidence was found; no conclusion can be drawn.")
    summary_parts.append(
        f"Applicability: {status_counts.get('confirmed', 0)} confirmed, "
        f"{status_counts.get('contradicted', 0)} contradicted, {status_counts.get('unknown', 0)} unknown."
    )
    missing = list(state.get("missing_information", []))
    missing += [check.details for check in checks if check.status == "unknown"]
    missing.append("No hypotheses were generated; hypothesis generation needs a configured model.")

    report = InvestigationReport(
        run_id=investigation_id,
        request=state.get("question", ""),
        target_scope=ReportScope(
            system=state.get("target_system"),
            environment=state.get("target_environment"),
        ),
        executive_summary=" ".join(summary_parts + ["Recommendations are not proof of a diagnosis."]),
        observed_facts=facts,
        document_references=document_refs,
        hypotheses=[],
        applicability_checks=checks,
        recommended_next_steps=_recommended_next_steps(checks, bool(chunks), real_count > 0),
        risks_and_required_approvals=[
            "No state-changing actions were requested or executed.",
            "Human approval is required for any remediation or configuration change.",
        ],
        missing_evidence=list(dict.fromkeys(missing)),
        uncertainty=[
            f"{check.status}: {check.prerequisite}. {check.details}"
            for check in checks
            if check.status != "confirmed"
        ],
        limitations=list(state.get("limitations", [])),
        investigation_plan=list(state.get("plan", [])),
    )
    known_ids = [ref.chunk_id for ref in document_refs] + [fact.evidence_id for fact in facts]
    validate_report_citations(report, known_ids)

    has_evidence = bool(chunks or observations)
    return {
        "report": report.model_dump(mode="json"),
        "status": "completed" if has_evidence else "insufficient_evidence",
    }


def finalize(state: InvestigationState, memory_manager: MemoryManager | None = None, audit_manager: Any = None) -> dict[str, Any]:
    investigation_id = state.get("investigation_id")
    report = state.get("report") or {}
    status = state.get("status", "completed")
    cited_ids = [chunk["chunk_id"] for chunk in state.get("retrieved_chunks", [])]
    cited_ids += [str(item.get("evidence_id", "")) for item in state.get("live_evidence", [])]
    if memory_manager is not None:
        try:
            from threadline.memory.models import InvestigationEpisode, TargetScope

            memory_manager.save_episode(
                InvestigationEpisode(
                    investigation_id=investigation_id,
                    symptom_summary=state.get("question", ""),
                    target_scope=TargetScope(
                        target_system=state.get("target_system"),
                        target_environment=state.get("target_environment"),
                    ),
                    diagnostic_steps=state.get("plan", []),
                    hypotheses_summary=[],
                    outcome_summary=report.get("executive_summary", ""),
                    verification_status="unverified",
                    source_evidence_ids=cited_ids,
                )
            )
        except Exception as exc:
            logger.error("episode save failed investigation_id=%s error=%s", investigation_id, type(exc).__name__)
        try:
            memory_manager.save_working_state(
                investigation_id,
                {
                    "question": state.get("question", ""),
                    "target_system": state.get("target_system"),
                    "target_environment": state.get("target_environment"),
                    "evidence_ids": state.get("retrieved_document_ids", []),
                    "iteration_count": state.get("iteration_count", 0),
                    "tool_call_count": state.get("tool_call_count", 0),
                    "status": status,
                },
            )
        except Exception as exc:
            logger.error("working state save failed investigation_id=%s error=%s", investigation_id, type(exc).__name__)
    record_event(
        audit_manager,
        investigation_id,
        "investigation.finalized",
        status=status,
        summary=report.get("executive_summary"),
        iteration_count=state.get("iteration_count", 0),
        tool_call_count=state.get("tool_call_count", 0),
        document_ids=state.get("retrieved_document_ids", []),
        observation_ids=[str(item.get("evidence_id", "")) for item in state.get("live_evidence", [])],
    )
    return {"status": status}


def route_after_evaluation(state: InvestigationState) -> str:
    if state.get("status") == "failed":
        return "generate_report"
    if state.get("retrieved_document_ids") or state.get("live_evidence"):
        return "generate_report"
    if state.get("iteration_count", 0) < min(int(state.get("max_iterations", 3)), 2):
        return "retrieve_more"
    return "generate_report"
