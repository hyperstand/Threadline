"""M5 memory manager implementing three separate memory types."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from threadline.config import Settings
from threadline.memory.checkpoint import CheckpointManager
from threadline.memory.models import (
    InvestigationEpisode,
    KnowledgeItem,
    RetrievedEpisode,
    SemanticKnowledge,
    TargetScope,
    WorkingState,
)
from threadline.persistence.models import WorkingStateModel, InvestigationEpisodeModel, KnowledgeItemModel
from threadline.redact import redact_secrets
from threadline.retrieval.interfaces import RetrievalFilters
from threadline.retrieval.hybrid import hybrid_search

from threadline.memory.models import InvestigationEpisode


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _redact_state(state: WorkingState) -> WorkingState:
    state.question = redact_secrets(state.question)
    state.plan = [redact_secrets(str(item)) for item in state.plan]
    state.hypotheses = [redact_secrets(str(item)) for item in state.hypotheses]
    state.completed_steps = [redact_secrets(str(item)) for item in state.completed_steps]
    state.pending_checks = [redact_secrets(str(item)) for item in state.pending_checks]
    # Evidence payloads remain external; only IDs are stored in working state.
    state.updated_at = _now()
    return state


class MemoryManager:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        session_factory,
        vector_adapter=None,
        embedding_provider=None,
        checkpoint_manager=None,
    ) -> None:
        self.settings = settings
        if isinstance(session_factory, tuple):
            _, session_factory = session_factory
        self._session_factory = session_factory
        self._embedding_provider = embedding_provider
        self._checkpointer = checkpoint_manager or CheckpointManager(settings)
        # Keep an in-memory cache only for the current process, never as authority.
        self._working_cache: dict[str, WorkingState] = {}

    # ----- Working memory -----

    def load_working_state(self, investigation_id: str) -> WorkingState | None:
        with self._session_factory() as session:
            model = session.get(WorkingStateModel, investigation_id)
            if model is not None:
                return WorkingState.model_validate(model.state)
        checkpoint_state = self._checkpointer.load(f"{investigation_id}:working")
        if isinstance(checkpoint_state, dict):
            try:
                return WorkingState.model_validate(checkpoint_state)
            except Exception:
                return None
        return None

    def save_working_state(
        self,
        investigation_id: str,
        state: WorkingState | dict[str, Any],
    ) -> WorkingState:
        if isinstance(state, dict):
            state = WorkingState(investigation_id=investigation_id, **state)
        if state.investigation_id != investigation_id:
            state.investigation_id = investigation_id
        state.graph_thread_id = state.graph_thread_id or investigation_id
        state = _redact_state(state)
        with self._session_factory() as session:
            model = session.get(WorkingStateModel, investigation_id)
            if model is None:
                model = WorkingStateModel(
                    investigation_id=investigation_id,
                    state=state.model_dump(mode="json"),
                    updated_at=_now(),
                )
                session.add(model)
            else:
                model.state = state.model_dump(mode="json")
                model.updated_at = _now()
            session.commit()
        checkpoint_thread_id = f"{investigation_id}:working"
        result = self._checkpointer.save(checkpoint_thread_id, state.model_dump(mode="json"))
        self._working_cache[investigation_id] = state
        return state

    # ----- Episodic memory -----

    def retrieve_episodes(
        self,
        query: str,
        target_scope: dict[str, Any] | None = None,
        limit: int = 5,
    ) -> list[RetrievedEpisode]:
        target_scope = target_scope or {}
        requested_system = target_scope.get("target_system") or target_scope.get("system")
        requested_environment = (
            target_scope.get("target_environment")
            or target_scope.get("environment")
            or target_scope.get("environment_scope")
        )
        tokens = _tokens(query)

        with self._session_factory() as session:
            rows = (
                session.query(InvestigationEpisodeModel)
                .order_by(InvestigationEpisodeModel.created_at.desc())
                .limit(200)
                .all()
            )
            candidates: list[tuple[int, InvestigationEpisodeModel]] = []
            for row in rows:
                row_scope = row.target_scope or {}
                row_system = row_scope.get("target_system") or row_scope.get("system")
                row_environment = (
                    row_scope.get("target_environment")
                    or row_scope.get("environment")
                    or row_scope.get("environment_scope")
                )
                if requested_system and row_system and row_system != requested_system:
                    continue
                if requested_environment and row_environment and row_environment != requested_environment:
                    continue
                haystack = " ".join(
                    [row.symptom_summary, row.outcome_summary, " ".join(row.hypotheses_summary or [])]
                ).lower()
                score = 1
                for token in tokens:
                    if token in haystack:
                        score += 1
                if requested_system and row_system == requested_system:
                    score += 2
                if requested_environment and row_environment == requested_environment:
                    score += 2
                candidates.append((score, row))

            candidates.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
            out: list[RetrievedEpisode] = []
            for score, row in candidates[: max(1, limit)]:
                episode = InvestigationEpisode(
                    id=row.id,
                    investigation_id=row.investigation_id,
                    symptom_summary=row.symptom_summary,
                    target_scope=TargetScope(**row.target_scope) if row.target_scope else TargetScope(),
                    diagnostic_steps=list(row.diagnostic_steps or []),
                    hypotheses_summary=list(row.hypotheses_summary or []),
                    outcome_summary=row.outcome_summary,
                    verification_status=row.verification_status,
                    source_evidence_ids=list(row.source_evidence_ids or []),
                    created_at=row.created_at,
                )
                age = (_now() - episode.created_at.replace(tzinfo=timezone.utc)
                       if episode.created_at.tzinfo is None
                       else (_now() - episode.created_at)).days
                retrieved = RetrievedEpisode(
                    episode=episode,
                    age_days=max(0, age),
                    historical=True,
                )
                out.append(retrieved)
            return out

    def save_episode(self, episode: InvestigationEpisode | dict[str, Any]) -> InvestigationEpisode:
        if isinstance(episode, dict):
            episode = InvestigationEpisode(**episode)
        if episode.id is None:
            episode.id = f"ep_{__import__('uuid').uuid4().hex[:12]}"
        with self._session_factory() as session:
            model = session.get(InvestigationEpisodeModel, episode.id)
            if model is None:
                model = InvestigationEpisodeModel(
                    id=episode.id,
                    investigation_id=episode.investigation_id,
                    symptom_summary=_redact_text(episode.symptom_summary),
                    target_scope=episode.target_scope.model_dump(mode="json"),
                    diagnostic_steps=[_redact_text(x) for x in episode.diagnostic_steps],
                    hypotheses_summary=[_redact_text(x) for x in episode.hypotheses_summary],
                    outcome_summary=_redact_text(episode.outcome_summary),
                    verification_status=episode.verification_status,
                    source_evidence_ids=list(episode.source_evidence_ids),
                    created_at=episode.created_at,
                )
                session.add(model)
            else:
                model.symptom_summary = _redact_text(episode.symptom_summary)
                model.target_scope = episode.target_scope.model_dump(mode="json")
                model.diagnostic_steps = [_redact_text(x) for x in episode.diagnostic_steps]
                model.hypotheses_summary = [_redact_text(x) for x in episode.hypotheses_summary]
                model.outcome_summary = _redact_text(episode.outcome_summary)
                model.verification_status = episode.verification_status
                model.source_evidence_ids = list(episode.source_evidence_ids)
            session.commit()
        return episode

    # ----- Semantic memory -----

    def retrieve_knowledge(
        self,
        query: str,
        filters: RetrievalFilters | None = None,
        limit: int = 8,
    ) -> list[SemanticKnowledge]:
        filters = filters or RetrievalFilters()
        out: list[SemanticKnowledge] = []
        with self._session_factory() as session:
            # Reuse hybrid retrieval for document/chunk-backed knowledge.
            try:
                hybrid_results = hybrid_search(
                    session,
                    query,
                    filters=filters,
                    limit=limit,
                    vector_adapter=self._vector_adapter,
                    embedding_provider=self._embedding_provider,
                )
            except Exception:
                hybrid_results = []
            for result in hybrid_results:
                out.append(
                    SemanticKnowledge(
                        id=result.chunk_id,
                        source_type="document_chunk",
                        content=result.content,
                        score=result.score,
                        source_id=result.source_name,
                        version=result.document_content_hash,
                        metadata={
                            "document_id": result.document_id,
                            "page_number": result.page_number,
                            "section_path": result.section_path,
                            "heading": result.heading,
                            "search_type": result.search_type,
                        },
                    )
                )

            # Approved reusable knowledge items.
            query_lc = (query or "").lower()
            items = session.query(KnowledgeItemModel).all()
            for model in items:
                haystack = f"{model.title} {model.content}".lower()
                score = 0.0
                for token in _tokens(query):
                    if token in haystack:
                        score += 0.3
                if not query_lc:
                    score = 0.5
                if model.review_status not in ("reviewed", "approved"):
                    continue
                if filters.document_type and getattr(model, "media_type", None):
                    pass
                out.append(
                    SemanticKnowledge(
                        id=model.id,
                        source_type="knowledge_item",
                        content=model.content,
                        score=score,
                        source_id=model.source_id,
                        version=model.version,
                        metadata={
                            "title": model.title,
                            "review_status": model.review_status,
                            "provenance": model.provenance,
                        },
                    )
                )

        out.sort(key=lambda item: item.score, reverse=True)
        return out[: max(1, limit)]

    def promote_knowledge(
        self,
        item: KnowledgeItem | dict[str, Any] | str,
        *,
        provenance: dict[str, Any],
        review_status: str,
    ) -> KnowledgeItem:
        if isinstance(item, str):
            knowledge = KnowledgeItem(title="Reviewed knowledge", content=item)
        elif isinstance(item, dict):
            knowledge = KnowledgeItem(**item)
        else:
            knowledge = item

        if review_status not in ("reviewed", "approved"):
            raise ValueError("Only reviewed or approved findings may be promoted.")
        if not provenance or not any(key in provenance for key in ("source_id", "document_id", "evidence_id", "citation")):
            raise ValueError("Knowledge promotion requires provenance.")

        knowledge.version = knowledge.version or provenance.get("version")
        knowledge.review_status = review_status
        knowledge.provenance = dict(provenance)
        with self._session_factory() as session:
            model = KnowledgeItemModel(
                title=knowledge.title,
                content=_redact_text(knowledge.content),
                source_id=knowledge.source_id or (provenance.get("source_id") if isinstance(provenance, dict) else None),
                system_scope=knowledge.system_scope,
                environment_scope=knowledge.environment_scope,
                version=knowledge.version,
                review_status=review_status,
                provenance=knowledge.provenance,
                tags=knowledge.tags,
            )
            session.add(model)
            session.flush()
            knowledge.id = model.id
            session.commit()
        return knowledge


def _tokens(value: str) -> list[str]:
    return [token for token in (value or "").lower().split() if token]


def _redact_text(value: str) -> str:
    return redact_secrets(str(value))
