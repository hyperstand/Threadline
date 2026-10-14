"""M2 ingestion pipeline: persist documents and chunks with provenance."""

from __future__ import annotations

from typing import Any

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from threadline.config import Settings
from threadline.ingestion.extractors import (
    ExtractedDocument,
    chunk_passages,
    detect_media_type,
    extract_document,
    sha256_bytes,
)
from threadline.persistence.models import DocumentChunkModel, DocumentModel
from threadline.redact import redact_secrets


class UnsupportedDocumentType(ValueError):
    pass


def _normalize_filename(filename: str) -> str:
    return (filename or "").strip() or "document"


def ingest_document(
    *,
    filename: str,
    data: bytes,
    session: Session,
    system_scope: str | None = None,
    environment_scope: str | None = None,
    settings: Settings | None = None,
    vector_adapter: Any | None = None,
    embedding_provider: Any | None = None,
) -> DocumentModel:
    safe_name = _normalize_filename(filename)
    media_type = detect_media_type(safe_name)
    if media_type is None:
        raise UnsupportedDocumentType(
            f"Unsupported document type for {safe_name!r}: supported types are PDF, DOCX, Markdown, TXT."
        )

    doc = DocumentModel(
        source_name=safe_name,
        media_type=media_type,
        content_hash=sha256_bytes(data),
        status="processing",
        system_scope=system_scope,
        environment_scope=environment_scope,
        source_metadata={"extractor": None, "byte_size": len(data)},
    )
    session.add(doc)
    session.flush()
    session.commit()
    session.refresh(doc)

    try:
        extracted: ExtractedDocument = extract_document(safe_name, data)
        chunks = chunk_passages(extracted.passages)
        chunk_models = []
        for chunk in chunks:
            model = DocumentChunkModel(
                document_id=doc.id,
                content=chunk.content,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                section_path=chunk.section_path,
                heading=chunk.heading,
                content_hash=chunk.content_hash,
            )
            session.add(model)
            chunk_models.append(model)
        session.flush()

        if vector_adapter is not None and embedding_provider is not None and chunks:
            texts = [chunk.content for chunk in chunks]
            embeddings = embedding_provider.embed_documents(texts)
            if len(embeddings) != len(chunks):
                raise ValueError("Embedding provider returned an unexpected number of vectors.")
            vector_adapter.upsert_many(
                [
                    (
                        chunk_model.id,
                        embedding,
                        {
                            "document_id": doc.id,
                            "source_name": doc.source_name,
                            "media_type": doc.media_type,
                            "system_scope": doc.system_scope,
                            "environment_scope": doc.environment_scope,
                            "status": doc.status,
                            "content_hash": doc.content_hash,
                            "version": doc.version_label,
                        },
                    )
                    for chunk_model, embedding in zip(chunk_models, embeddings)
                ]
            )

        doc.status = "indexed"
        doc.source_metadata = {
            "extractor": extracted.extractor,
            "page_count": extracted.page_count,
            "chunk_count": len(chunks),
            "byte_size": len(data),
            "embedding_count": len(chunks) if vector_adapter is not None and embedding_provider is not None else 0,
        }
        doc.updated_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(doc)
        try:
            from threadline.retrieval.keyword import sync_fts
            sync_fts(session)
        except Exception:
            pass
        return doc
    except Exception as exc:
        session.rollback()
        try:
            failed_doc = session.get(DocumentModel, doc.id)
            if failed_doc is not None:
                failed_doc.status = "failed"
                failed_doc.source_metadata = {
                    "error": redact_secrets(str(exc)),
                    "byte_size": len(data),
                }
                failed_doc.updated_at = datetime.now(timezone.utc)
                session.commit()
                session.refresh(failed_doc)
                return failed_doc
        except Exception:
            session.rollback()
            session.rollback()
        raise RuntimeError(
            f"Ingestion failed for {safe_name}: {type(exc).__name__}: {redact_secrets(str(exc))}"
        ) from exc
