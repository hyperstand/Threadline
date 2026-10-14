"""M4 hybrid keyword + vector retrieval."""

from __future__ import annotations

from threadline.retrieval.interfaces import RetrievalFilters, RetrievalResult
from threadline.retrieval.keyword import keyword_search
from threadline.retrieval.vector import VectorHit


def _apply_filters(result: RetrievalResult, filters: RetrievalFilters) -> bool:
    from threadline.retrieval.keyword import _match_document_type

    if filters.document_type and not _match_document_type(
        # Reconstruct a tiny compatible object for filter helper.
        type("_Doc", (), {"media_type": result.media_type}),
        filters.document_type,
    ):
        return False
    if filters.system_scope and result.system_scope not in (None, filters.system_scope):
        return False
    if filters.environment_scope and result.environment_scope not in (None, filters.environment_scope):
        return False
    if filters.status and result.status != filters.status:
        return False
    if filters.version and result.version_label not in (None, filters.version) and result.document_content_hash != filters.version:
        return False
    return True


def vector_search(
    session,
    query: str,
    filters: RetrievalFilters | None,
    limit: int,
    vector_adapter,
    embedding_provider,
) -> list[RetrievalResult]:
    from threadline.persistence.models import DocumentChunkModel

    f = filters or RetrievalFilters()
    if vector_adapter is None or embedding_provider is None:
        return []
    if not query or not query.strip():
        return []

    query_vector = embedding_provider.embed_query(query)
    candidate_limit = max(limit * 4, 50)
    hits: list[VectorHit] = vector_adapter.search(query_vector, limit=candidate_limit)
    if not hits:
        return []

    chunk_ids = [hit.chunk_id for hit in hits]
    chunks = session.query(DocumentChunkModel).filter(DocumentChunkModel.id.in_(chunk_ids)).all()
    chunk_by_id = {chunk.id: chunk for chunk in chunks}
    hit_by_id = {hit.chunk_id: hit for hit in hits}

    results: list[RetrievalResult] = []
    for chunk_id, chunk in chunk_by_id.items():
        hit = hit_by_id.get(chunk_id)
        if hit is None:
            continue
        doc = chunk.document
        result = RetrievalResult(
            chunk_id=chunk.id,
            document_id=doc.id,
            source_name=doc.source_name,
            media_type=doc.media_type,
            content=chunk.content,
            content_hash=chunk.content_hash,
            page_number=chunk.page_number,
            section_path=chunk.section_path,
            heading=chunk.heading,
            document_content_hash=doc.content_hash,
            version_label=doc.version_label,
            system_scope=doc.system_scope,
            environment_scope=doc.environment_scope,
            status=doc.status,
            score=float(hit.score),
            search_type="vector",
            semantic_score=float(hit.score),
        )
        if not _apply_filters(result, f):
            continue
        results.append(result)

    results.sort(key=lambda item: item.score, reverse=True)
    return results[: max(1, limit)]


def _fuse(
    keyword_results: list[RetrievalResult],
    vector_results: list[RetrievalResult],
    limit: int,
) -> list[RetrievalResult]:
    keyword_rank = {result.chunk_id: index + 1 for index, result in enumerate(keyword_results)}
    vector_rank = {result.chunk_id: index + 1 for index, result in enumerate(vector_results)}
    keyword_by_id = {result.chunk_id: result for result in keyword_results}
    vector_by_id = {result.chunk_id: result for result in vector_results}

    fused: list[RetrievalResult] = []
    for chunk_id in set(keyword_by_id) | set(vector_by_id):
        keyword_result = keyword_by_id.get(chunk_id)
        vector_result = vector_by_id.get(chunk_id)

        keyword_score = keyword_result.score if keyword_result is not None else None
        semantic_score = vector_result.score if vector_result is not None else None

        if keyword_result is not None and vector_result is not None:
            rank_component = 1.0 / (60 + (keyword_rank.get(chunk_id, 999))) + 1.0 / (
                60 + (vector_rank.get(chunk_id, 999))
            )
            score = rank_component
            search_type = "hybrid"
            result = keyword_result
        elif keyword_result is not None:
            score = keyword_score or 0.0
            search_type = "keyword"
            result = keyword_result
        else:
            score = semantic_score or 0.0
            search_type = "vector"
            result = vector_result

        # Preserve provenance from whichever store supplies the chunk record.
        merged = RetrievalResult(
            chunk_id=result.chunk_id,
            document_id=result.document_id,
            source_name=result.source_name,
            media_type=result.media_type,
            content=result.content,
            content_hash=result.content_hash,
            page_number=result.page_number,
            section_path=result.section_path,
            heading=result.heading,
            document_content_hash=result.document_content_hash,
            version_label=result.version_label,
            system_scope=result.system_scope,
            environment_scope=result.environment_scope,
            status=result.status,
            score=score,
            search_type=search_type,
            keyword_score=keyword_score,
            semantic_score=semantic_score,
            fusion_score=score,
        )
        fused.append(merged)

    fused.sort(key=lambda item: (item.score, item.chunk_id), reverse=True)
    return fused[: max(1, limit)]


def hybrid_search(
    session,
    query: str,
    filters: RetrievalFilters | None = None,
    limit: int = 8,
    mode: str = "hybrid",
    vector_adapter=None,
    embedding_provider=None,
) -> list[RetrievalResult]:
    f = filters or RetrievalFilters()
    mode = mode or "hybrid"
    keyword_results: list[RetrievalResult] = []
    vector_results: list[RetrievalResult] = []

    if mode in {"keyword", "hybrid"}:
        keyword_results = keyword_search(session, query, filters=f, limit=limit)
    if mode in {"vector", "hybrid"}:
        vector_results = vector_search(
            session,
            query,
            filters=f,
            limit=limit,
            vector_adapter=vector_adapter,
            embedding_provider=embedding_provider,
        )

    if mode == "keyword":
        return keyword_results
    if mode == "vector":
        return vector_results
    return _fuse(keyword_results, vector_results, limit)
