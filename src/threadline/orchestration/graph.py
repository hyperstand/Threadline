"""M6/M8 bounded investigation LangGraph with per-node audit events (PRD FR-11)."""

from __future__ import annotations

from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from threadline.audit import record_event
from threadline.integrations.goose import FakeGooseAdapter
from threadline.memory.manager import MemoryManager
from threadline.orchestration.nodes import (
    assess_applicability,
    evaluate_evidence,
    finalize as finalize_node,
    generate_report as generate_report_node,
    gather_live_evidence as gather_node,
    initialize as initialize_node,
    normalize_evidence,
    plan_investigation,
    resolve_context as resolve_context_node,
    retrieve_documents as retrieve_documents_node,
    route_after_evaluation,
)
from threadline.orchestration.state import InvestigationState
from threadline.redact import redact_secrets


def build_investigation_graph(
    *,
    settings: Any,
    checkpoint_manager: Any,
    memory_manager: MemoryManager,
    goose_adapter: FakeGooseAdapter,
    audit_manager: Any = None,
    document_retrieval=None,
    command: str = "run",
):
    checkpointer = getattr(checkpoint_manager, "_graph", None) and checkpoint_manager._saver

    graph = StateGraph(InvestigationState)

    def audited(node_name: str, node_fn: Callable[[InvestigationState], dict[str, Any]]):
        def run(state: InvestigationState) -> dict[str, Any]:
            investigation_id = state.get("investigation_id")
            try:
                update = node_fn(state)
            except Exception as exc:
                record_event(
                    audit_manager,
                    investigation_id,
                    "workflow.node_failed",
                    status="failed",
                    node=node_name,
                    error=redact_secrets(str(exc))[:300],
                )
                raise
            record_event(audit_manager, investigation_id, "workflow.node_completed", node=node_name)
            return update

        return run

    def initialize(state):
        return initialize_node(state, settings)

    def resolve_context(state):
        return resolve_context_node(state, memory_manager)

    def plan(state):
        return plan_investigation(state, memory_manager)

    def retrieve(state):
        def retrieval_func(query, filters, limit):
            if callable(document_retrieval):
                return document_retrieval(query, filters, limit)
            return memory_manager.retrieve_knowledge(query, filters=filters, limit=limit)

        return retrieve_documents_node(state, retrieval_func, state.get("question"), audit_manager=audit_manager)

    def gather(state):
        return gather_node(
            state,
            goose_adapter,
            getattr(goose_adapter, "policy", goose_adapter) if goose_adapter is not None else None,
            state.get("target_system"),
            state.get("target_environment"),
            audit_manager=audit_manager,
        )

    def applicability(state):
        return assess_applicability(state, audit_manager=audit_manager)

    def evaluate(state):
        update, _ = evaluate_evidence(state)
        return update

    def finalizer(state):
        return finalize_node(state, memory_manager, audit_manager)

    nodes: dict[str, Callable[[InvestigationState], dict[str, Any]]] = {
        "initialize": initialize,
        "resolve_context": resolve_context,
        "plan_investigation": plan,
        "retrieve_documents": retrieve,
        "gather_live_evidence": gather,
        "normalize_evidence": normalize_evidence,
        "assess_applicability": applicability,
        "evaluate_evidence": evaluate,
        "generate_report": generate_report_node,
        "finalize": finalizer,
    }
    for name, node_fn in nodes.items():
        graph.add_node(name, audited(name, node_fn))

    graph.add_edge(START, "initialize")
    graph.add_edge("initialize", "resolve_context")
    graph.add_edge("resolve_context", "plan_investigation")

    def route_after_plan(state):
        if state.get("status") in {"failed", "insufficient_evidence"}:
            return "generate_report"
        return "retrieve_documents"

    graph.add_conditional_edges("plan_investigation", route_after_plan, {"retrieve_documents": "retrieve_documents", "generate_report": "generate_report"})
    graph.add_edge("retrieve_documents", "gather_live_evidence")
    graph.add_edge("gather_live_evidence", "normalize_evidence")
    graph.add_edge("normalize_evidence", "assess_applicability")
    graph.add_edge("assess_applicability", "evaluate_evidence")
    graph.add_conditional_edges(
        "evaluate_evidence",
        route_after_evaluation,
        {
            "retrieve_more": "plan_investigation",
            "generate_report": "generate_report",
        },
    )
    graph.add_edge("generate_report", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer)


def run_investigation(
    graph,
    *,
    investigation_id: str,
    question: str,
    target_system: str | None,
    target_environment: str | None,
    mode: str = "live",
    memory_manager: MemoryManager | None = None,
):
    initial_state: InvestigationState = {
        "investigation_id": investigation_id,
        "question": question,
        "target_system": target_system,
        "target_environment": target_environment,
        "mode": mode,
        "max_iterations": 3,
        "max_tool_calls": 10,
        "iteration_count": 0,
        "tool_call_count": 0,
        "plan": [],
        "retrieved_document_ids": [],
        "retrieved_chunks": [],
        "episode_ids": [],
        "live_evidence": [],
        "missing_information": [],
        "limitations": [],
        "status": "queued",
        "report": None,
    }
    config = {"configurable": {"thread_id": investigation_id}}
    return graph.invoke(initial_state, config)


def resume_investigation(graph, *, investigation_id: str, update: dict[str, Any] | None = None):
    config = {"configurable": {"thread_id": investigation_id}}
    if update:
        graph.update_state(config, update)
    return graph.invoke(None, config)
