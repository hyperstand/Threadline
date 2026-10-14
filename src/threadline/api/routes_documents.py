"""M2 document routes."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from threadline.ingestion.pipeline import UnsupportedDocumentType, ingest_document
from threadline.api.schemas import DocumentRead

router = APIRouter(prefix="/api/v1", tags=["documents"])


@router.post("/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload_document(request: Request, file: UploadFile = File(...)) -> DocumentRead:
    data = file.file.read()
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        try:
            doc = ingest_document(
                filename=file.filename or "document",
                data=data,
                session=session,
                vector_adapter=request.app.state.vector_adapter,
                embedding_provider=request.app.state.embedding_provider,
            )
        except UnsupportedDocumentType as exc:
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ingestion failed")
        result = DocumentRead.model_validate(doc)
    return result


@router.get("/documents", response_model=list[DocumentRead])
def list_documents(request: Request) -> list[DocumentRead]:
    from threadline.persistence.models import DocumentModel

    session_factory = request.app.state.session_factory
    with session_factory() as session:
        docs = session.query(DocumentModel).order_by(DocumentModel.created_at.desc()).all()
        result = [DocumentRead.model_validate(d) for d in docs]
    return result


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(request: Request, document_id: str) -> DocumentRead:
    from threadline.persistence.models import DocumentModel

    session_factory = request.app.state.session_factory
    with session_factory() as session:
        doc = session.get(DocumentModel, document_id)
        if doc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        result = DocumentRead.model_validate(doc)
    return result
