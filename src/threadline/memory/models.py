"""M5 functional memory models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TargetScope(BaseModel):
    user_id: str | None = None
    target_system: str | None = None
    target_environment: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class WorkingState(BaseModel):
    investigation_id: str
    graph_thread_id: str | None = None
    question: str
    target_system: str | None = None
    target_environment: str | None = None
    plan: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    completed_steps: list[str] = Field(default_factory=list)
    pending_checks: list[str] = Field(default_factory=list)
    iteration_count: int = 0
    tool_call_count: int = 0
    status: str = "queued"
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class InvestigationEpisode(BaseModel):
    id: str | None = None
    investigation_id: str
    symptom_summary: str
    target_scope: TargetScope = Field(default_factory=TargetScope)
    diagnostic_steps: list[str] = Field(default_factory=list)
    hypotheses_summary: list[str] = Field(default_factory=list)
    outcome_summary: str = ""
    verification_status: Literal[
        "verified", "partially_verified", "unverified", "unresolved"
    ] = "unresolved"
    source_evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)


class RetrievedEpisode(BaseModel):
    episode: InvestigationEpisode
    age_days: int = 0
    historical: bool = True


class KnowledgeItem(BaseModel):
    id: str | None = None
    title: str
    content: str
    source_id: str | None = None
    system_scope: str | None = None
    environment_scope: str | None = None
    version: str | None = None
    review_status: Literal["draft", "reviewed", "approved"] = "draft"
    provenance: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)


class SemanticKnowledge(BaseModel):
    id: str
    source_type: str
    content: str
    score: float = 0.0
    source_id: str | None = None
    version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
