"""M3 retrieval interfaces and filters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RetrievalFilters:
    document_type: str | None = None
    system_scope: str | None = None
    environment_scope: str | None = None
    status: str | None = None
    version: str | None = None
    media_scope: str | None = None


@dataclass
class RetrievalResult:
    chunk_id: str
    document_id: str
    source_name: str
    media_type: str
    content: str
    content_hash: str
    page_number: int | None = None
    section_path: str | None = None
    heading: str | None = None
    document_content_hash: str | None = None
    version_label: str | None = None
    system_scope: str | None = None
    environment_scope: str | None = None
    status: str | None = None
    score: float = 0.0
    search_type: str = "keyword"
    keyword_score: float | None = None
    semantic_score: float | None = None
    fusion_score: float | None = None


def validate_filters(filters: RetrievalFilters | None) -> RetrievalFilters:
    return filters or RetrievalFilters()
