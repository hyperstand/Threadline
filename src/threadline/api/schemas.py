"""Pydantic API schemas (M2/M3)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    chunk_index: int
    page_number: int | None
    section_path: str | None
    heading: str | None
    content: str
    content_hash: str
    created_at: datetime


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_name: str
    media_type: str
    content_hash: str
    version_label: str | None
    status: str
    system_scope: str | None
    environment_scope: str | None
    source_metadata: dict | None
    created_at: datetime
    updated_at: datetime
    chunks: list[DocumentChunkRead] = []


class RetrievalResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: str
    document_id: str
    source_name: str
    media_type: str
    content: str
    content_hash: str
    page_number: int | None
    section_path: str | None
    heading: str | None
    document_content_hash: str | None
    version_label: str | None
    system_scope: str | None
    environment_scope: str | None
    status: str | None
    score: float
    search_type: str
    keyword_score: float | None = None
    semantic_score: float | None = None
    fusion_score: float | None = None


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[RetrievalResultRead]


class AnswerRequest(BaseModel):
    question: str
    limit: int = 5
    document_type: str | None = None
    system_scope: str | None = None
    environment_scope: str | None = None
    status: str | None = None
    version: str | None = None


class AnswerResponse(BaseModel):
    question: str
    answer: str
    citations: list[str]
    citation_check: dict
    results: list[RetrievalResultRead]
