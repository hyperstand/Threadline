"""M6 bounded investigation state."""

from __future__ import annotations

from typing import Any, TypedDict


class InvestigationState(TypedDict, total=False):
    investigation_id: str
    question: str
    target_system: str | None
    target_environment: str | None
    mode: str
    max_iterations: int
    max_tool_calls: int
    iteration_count: int
    tool_call_count: int
    plan: list[str]
    retrieved_document_ids: list[str]
    retrieved_chunks: list[dict[str, Any]]
    episode_ids: list[str]
    live_evidence: list[dict[str, Any]]
    hypotheses: list[Any]
    applicability_checks: list[dict[str, Any]]
    missing_information: list[str]
    limitations: list[str]
    status: str
    report: dict[str, Any] | None
