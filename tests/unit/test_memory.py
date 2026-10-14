"""M5 tests: working, episodic, semantic memory separation and checkpoint recovery."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from threadline.config import Settings
from threadline.memory.models import (
    InvestigationEpisode,
    KnowledgeItem,
    TargetScope,
    WorkingState,
)
from threadline.memory.manager import MemoryManager
from threadline.persistence.database import create_session_factory, init_storage


def _factory(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    settings = Settings(
        THREADLINE_ENV="test",
        DATABASE_URL=url,
        VECTOR_ENABLED=False,
    )
    init_storage(settings)
    return url, settings, create_session_factory(settings)


def test_working_state_roundtrip_and_redaction(tmp_path):
    url, settings, sf = _factory(tmp_path)
    mm = MemoryManager(settings=settings, session_factory=sf)
    saved = mm.save_working_state(
        "inv-1",
        WorkingState(investigation_id="inv-1", question="token: secret123", status="running"),
    )
    assert saved.question == "token=[REDACTED]"
    loaded = mm.load_working_state("inv-1")
    assert loaded is not None
    assert loaded.question == "token=[REDACTED]"
    assert loaded.investigation_id == "inv-1"
    assert mm.load_working_state("inv-2") is None


def test_checkpoint_can_resume_working_state(tmp_path):
    url, settings, sf = _factory(tmp_path)
    mm = MemoryManager(settings=settings, session_factory=sf)
    mm.save_working_state(
        "inv-1",
        WorkingState(investigation_id="inv-1", question="hello", plan=["check"], status="running"),
    )
    again = MemoryManager(settings=settings, session_factory=sf)
    # DB state should load first.
    loaded = again.load_working_state("inv-1")
    assert loaded is not None
    assert loaded.plan == ["check"]
    # Checkpoint is also successfully populated.
    values = again._checkpointer.load("inv-1:working")
    assert values is not None
    assert values.get("status") == "running"
    assert isinstance(values.get("plan"), list)


def test_episodic_retrieval_filters_by_target_scope(tmp_path):
    url, settings, sf = _factory(tmp_path)
    mm = MemoryManager(settings=settings, session_factory=sf)
    mm.save_episode(
        InvestigationEpisode(
            investigation_id="old-1",
            symptom_summary="service failure",
            target_scope=TargetScope(target_system="svc-a", target_environment="prod"),
            outcome_summary="resolved",
            verification_status="verified",
        )
    )
    mm.save_episode(
        InvestigationEpisode(
            investigation_id="old-2",
            symptom_summary="service failure",
            target_scope=TargetScope(target_system="svc-b", target_environment="prod"),
            outcome_summary="resolved",
            verification_status="verified",
        )
    )
    results = mm.retrieve_episodes(
        "service failure",
        target_scope={"target_system": "svc-a", "target_environment": "prod"},
        limit=5,
    )
    assert len(results) == 1
    assert results[0].episode.target_scope.target_system == "svc-a"
    assert results[0].historical is True
    assert results[0].age_days >= 0


def test_knowledge_promotion_requires_review_and_provenance(tmp_path):
    url, settings, sf = _factory(tmp_path)
    mm = MemoryManager(settings=settings, session_factory=sf)
    with pytest.raises(ValueError):
        mm.promote_knowledge("unreviewed", provenance={"source_id": "doc1"}, review_status="draft")
    with pytest.raises(ValueError):
        mm.promote_knowledge("no provenance", provenance={}, review_status="approved")

    item = mm.promote_knowledge(
        "Verified safe procedure",
        provenance={"source_id": "doc1", "evidence_id": "ev1", "version": "v1"},
        review_status="approved",
    )
    assert item.review_status == "approved"
    assert item.version == "v1"

    knowledge = mm.retrieve_knowledge("procedure", limit=8)
    assert any(k.source_type == "knowledge_item" and "verified" in k.content.lower() for k in knowledge)


def test_working_state_is_separate_from_episodic(tmp_path):
    url, settings, sf = _factory(tmp_path)
    mm = MemoryManager(settings=settings, session_factory=sf)
    mm.save_working_state(
        "live",
        WorkingState(investigation_id="live", question="live question", status="running"),
    )
    mm.save_episode(
        InvestigationEpisode(
            investigation_id="old",
            symptom_summary="old issue",
            outcome_summary="old resolution",
            verification_status="verified",
        )
    )
    episodes = mm.retrieve_episodes("issue")
    assert all(ep.episode.investigation_id == "old" for ep in episodes)
    loaded = mm.load_working_state("live")
    assert loaded is not None and loaded.question == "live question"
    # Episodic data is not automatically inserted into working state.
    assert mm.load_working_state("old") is None