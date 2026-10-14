"""FTS5 keyword retrieval with SQLite and result provenance."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

from threadline.retrieval import RetrievalFilters, RetrievalResult
from threadline.persistence.database import init_storage  # noqa: F401  ensures metadata
from threadline.persistence.models import DocumentModel


FTS_TABLE = "document_chunks_fts"


def _match_document_type(document, requested: str | None) -> bool:
    if not requested:
        return True
    requested = requested.lower().strip()
    media = (document.media_type or "").lower()
    # Accept MIME, extension, or friendly labels.
    wanted_candidates = {requested, "." + requested.lstrip(".")}
    if requested in ("pdf", "application/pdf"):
        return media == "application/pdf"
    if requested in ("docx", "document", "word"):
        return media.endswith("wordprocessingml.document")
    if requested in ("markdown", "md"):
        return media in ("text/markdown",)
    if requested in ("txt", "text", "plain"):
        return media == "text/plain"
    return media == requested or any(c in media for c in wanted_candidates)


def ensure_fts(session) -> None:
    session.execute(
        text(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE} USING fts5("
            "chunk_id UNINDEXED, document_id UNINDEXED, source_name, content)"
        )
    )
    session.commit()


def sync_fts(session) -> None:
    ensure_fts(session)
    session.execute(
        text(
            f"INSERT INTO {FTS_TABLE}(chunk_id, document_id, source_name, content) "
            "SELECT c.id, c.document_id, d.source_name, c.content "
            "FROM document_chunks c JOIN documents d ON d.id = c.document_id "
            f"WHERE NOT EXISTS (SELECT 1 FROM {FTS_TABLE} f WHERE f.chunk_id = c.id)"
        )
    )
    session.commit()


def _build_fts_query(query: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9_]+", query or "")
    if not tokens:
        return ""
    return " ".join(f'"{t.lower()}"' for t in tokens)


def keyword_search(session, query: str, filters: RetrievalFilters | None = None, limit: int = 8) -> list[RetrievalResult]:
    from sqlalchemy.orm import Session as SASession  # noqa: F401

    f = filters or RetrievalFilters()
    ensure_fts(session)
    sync_fts(session)

    q = _build_fts_query(query)
    if not q:
        return []

    limit = max(1, min(int(limit or 8), 100))
    # Pull a larger candidate set so filters can be applied without starving.
    fetch_limit = max(limit * 4, 50)

    sql = text(
        f"""
        SELECT f.chunk_id AS chunk_id, f.rank AS rank
        FROM {FTS_TABLE} f
        WHERE {FTS_TABLE} MATCH :q
        ORDER BY f.rank
        LIMIT :fetch_limit
        """
    )
    try:
        rows = session.execute(sql, {"q": q, "fetch_limit": fetch_limit}).mappings().all()
    except Exception:
        # If FTS syntax fails despite sanitization, fall back to direct substring search.
        return _substring_search(session, query, f, limit)

    chunk_ids = [r["chunk_id"] for r in rows]
    if not chunk_ids:
        return []
    rank_by_chunk = {r["chunk_id"]: (r["rank"] if r.get("rank") is not None else 0.0) for r in rows}

    from threadline.persistence.models import DocumentChunkModel

    chunks = (
        session.query(DocumentChunkModel)
        .join(DocumentModel)
        .filter(DocumentChunkModel.id.in_(chunk_ids))
        .all()
    )
    doc_by_id = {}
    chunk_by_id = {}
    for c in chunks:
        chunk_by_id[c.id] = c
        doc_by_id[c.document_id] = c.document

    ordered: list[RetrievalResult] = []
    for cid in chunk_ids:
        chunk = chunk_by_id.get(cid)
        if chunk is None:
            continue
        doc = doc_by_id[chunk.document_id] or chunk.document
        if doc is None:
            continue
        # filters
        if f.document_type and not _match_document_type(doc, f.document_type):
            continue
        if f.system_scope and doc.system_scope not in (None, f.system_scope):
            continue
        if f.environment_scope and doc.environment_scope not in (None, f.environment_scope):
            continue
        if f.status and doc.status != f.status:
            continue
        if f.version and doc.version_label not in (None, f.version) and doc.content_hash != f.version:
            continue
        if f.media_scope and doc.environment_scope != f.media_scope:
            continue
        rank = float(rank_by_chunk.get(cid, 0.0))
        # FTS rank: lower is better; convert to a positive score.
        score = 1.0 / (1.0 + abs(rank))
        ordered.append(
            RetrievalResult(
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
                score=score,
                search_type="keyword",
            )
        )
        if len(ordered) >= limit:
            break
    return ordered


def _substring_search(session, query: str, f: RetrievalFilters, limit: int) -> list[RetrievalResult]:
    from threadline.persistence.models import DocumentChunkModel

    like = f"%{query}%"
    chunks = (
        session.query(DocumentChunkModel)
        .join(DocumentModel)
        .filter(DocumentChunkModel.content.ilike(like))
        .all()
    )
    out = []
    for chunk in chunks:
        doc = chunk.document
        if f.document_type and not _match_document_type(doc, f.document_type):
            continue
        if f.system_scope and doc.system_scope not in (None, f.system_scope):
            continue
        if f.environment_scope and doc.environment_scope not in (None, f.environment_scope):
            continue
        if f.status and doc.status != f.status:
            continue
        if f.version and doc.version_label not in (None, f.version) and doc.content_hash != f.version:
            continue
        out.append(
            RetrievalResult(
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
                score=0.5,
                search_type="keyword-substring",
            )
        )
        if len(out) >= limit:
            break
    return out
