"""M3 search and citation-backed answer routes."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request

from threadline.api.schemas import (
    AnswerRequest,
    AnswerResponse,
    RetrievalResultRead,
    SearchResponse,
)
from threadline.evidence.citations import validate_citation_ids
from threadline.answers import build_cited_answer
from threadline.retrieval import RetrievalFilters
from threadline.retrieval.hybrid import hybrid_search

router = APIRouter(prefix="/api/v1", tags=["retrieval"])


def _filters_for_request(
    *,
    document_type=None,
    system_scope=None,
    environment_scope=None,
    status=None,
    version=None,
):
    return RetrievalFilters(
        document_type=document_type,
        system_scope=system_scope,
        environment_scope=environment_scope,
        status=status,
        version=version,
    )


def _to_read(r) -> RetrievalResultRead:
    return RetrievalResultRead(
        chunk_id=r.chunk_id,
        document_id=r.document_id,
        source_name=r.source_name,
        media_type=r.media_type,
        content=r.content,
        content_hash=r.content_hash,
        page_number=r.page_number,
        section_path=r.section_path,
        heading=r.heading,
        document_content_hash=r.document_content_hash,
        version_label=r.version_label,
        system_scope=r.system_scope,
        environment_scope=r.environment_scope,
        status=r.status,
        score=r.score,
        search_type=r.search_type,
        keyword_score=r.keyword_score,
        semantic_score=r.semantic_score,
        fusion_score=r.fusion_score,
    )


@router.get("/search", response_model=SearchResponse)
def search(
    request: Request,
    q: str = "",
    limit: int = 8,
    mode: str = "hybrid",
    document_type: str | None = None,
    system_scope: str | None = None,
    environment_scope: str | None = None,
    status: str | None = None,
    version: str | None = None,
) -> SearchResponse:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        filters = _filters_for_request(
            document_type=document_type,
            system_scope=system_scope,
            environment_scope=environment_scope,
            status=status,
            version=version,
        )
        results = hybrid_search(
            session,
            q,
            filters=filters,
            limit=limit,
            mode=mode,
            vector_adapter=request.app.state.vector_adapter,
            embedding_provider=request.app.state.embedding_provider,
        )
    return SearchResponse(query=q, total=len(results), results=[_to_read(r) for r in results])


@router.post("/answers", response_model=AnswerResponse)
def answer(request: Request, body: AnswerRequest) -> AnswerResponse:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        filters = _filters_for_request(
            document_type=body.document_type,
            system_scope=body.system_scope,
            environment_scope=body.environment_scope,
            status=body.status,
            version=body.version,
        )
        results = hybrid_search(
            session,
            body.question,
            filters=filters,
            limit=max(body.limit, 5),
            vector_adapter=request.app.state.vector_adapter,
            embedding_provider=request.app.state.embedding_provider,
        )
        known_ids = {r.chunk_id for r in results}
    cited = build_cited_answer(body.question, results, max_results=body.limit)
    validation = validate_citation_ids(cited.citations, known_ids)
    return AnswerResponse(
        question=body.question,
        answer=cited.answer,
        citations=cited.citations,
        citation_check={
            "all_valid": validation.all_valid,
            "valid": validation.valid,
            "invalid": validation.invalid,
        },
        results=[_to_read(r) for r in cited.results],
    )
