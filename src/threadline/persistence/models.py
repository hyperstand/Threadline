"""SQLAlchemy ORM models for Threadline documents (M2 ingestion provenance)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from threadline.persistence.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class DocumentModel(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    source_name: Mapped[str] = mapped_column(String(512), nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    version_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    system_scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    environment_scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now, nullable=False)

    chunks: Mapped[list["DocumentChunkModel"]] = relationship(
        "DocumentChunkModel",
        cascade="all, delete-orphan",
        back_populates="document",
        order_by="DocumentChunkModel.chunk_index",
    )


class DocumentChunkModel(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    heading: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now, nullable=False)

    document: Mapped[DocumentModel] = relationship("DocumentModel", back_populates="chunks")


class InvestigationModel(Base):
    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    target_system: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_environment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    graph_thread_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime] = mapped_column(default=_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    audit_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class WorkingStateModel(Base):
    __tablename__ = "working_states"

    investigation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now, nullable=False)


class InvestigationEpisodeModel(Base):
    __tablename__ = "investigation_episodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symptom_summary: Mapped[str] = mapped_column(Text, nullable=False)
    target_scope: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    diagnostic_steps: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    hypotheses_summary: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    outcome_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    verification_status: Mapped[str] = mapped_column(String(32), default="unresolved", nullable=False)
    source_evidence_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_now, nullable=False)


class AuditEventModel(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    investigation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(default=_now, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    safe_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

class KnowledgeItemModel(Base):
    __tablename__ = "knowledge_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    system_scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    environment_scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_now, nullable=False)
