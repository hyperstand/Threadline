"""M6 investigation routes."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from threadline.integrations.goose import FakeGooseAdapter
from threadline.orchestration.graph import run_investigation, resume_investigation
from threadline.persistence.models import InvestigationModel

router = APIRouter(prefix="/api/v1", tags=["investigations"])

class InvestigationCreate(BaseModel):
    question: str
    target_system: str
    target_environment: str
    mode: str = "live"

class InvestigationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    question: str
    target_system: str | None
    target_environment: str | None
    status: str
    summary: str | None = None
    report: dict[str, Any] | None = None

@router.post("/investigations", response_model=InvestigationRead, status_code=status.HTTP_201_CREATED)
def create_investigation(request: Request, body: InvestigationCreate) -> InvestigationRead:
    session_factory = request.app.state.session_factory
    graph = request.app.state.investigation_graph
    memory_manager = request.app.state.memory_manager
    investigation_id = str(uuid.uuid4())
    with session_factory() as session:
        record = InvestigationModel(
            id=investigation_id,
            question=body.question,
            target_system=body.target_system,
            target_environment=body.target_environment,
            status="queued",
            graph_thread_id=investigation_id,
        )
        session.add(record)
        session.commit()
    try:
        result = run_investigation(
            graph,
            investigation_id=investigation_id,
            question=body.question,
            target_system=body.target_system,
            target_environment=body.target_environment,
            mode=body.mode,
            memory_manager=memory_manager,
        )
    except Exception as exc:
        result = {"status": "failed", "report": {"summary": str(exc)}}
    final_status = result.get("status", "failed")
    report = result.get("report")
    with session_factory() as session:
        record = session.get(InvestigationModel, investigation_id)
        if record is not None:
            record.status = final_status
            record.summary = (report or {}).get("summary") if isinstance(report, dict) else None
            record.report = report if isinstance(report, dict) else None
            session.commit()
    return InvestigationRead(
        id=investigation_id,
        question=body.question,
        target_system=body.target_system,
        target_environment=body.target_environment,
        status=final_status,
        summary=record.summary if record else None,
        report=report,
    )

@router.get("/investigations/{investigation_id}", response_model=InvestigationRead)
def get_investigation(request: Request, investigation_id: str) -> InvestigationRead:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        record = session.get(InvestigationModel, investigation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return InvestigationRead(
        id=record.id,
        question=record.question,
        target_system=record.target_system,
        target_environment=record.target_environment,
        status=record.status,
        summary=record.summary,
        report=record.report,
    )

@router.post("/investigations/{investigation_id}/resume", response_model=InvestigationRead)
def resume(request: Request, investigation_id: str) -> InvestigationRead:
    graph = request.app.state.investigation_graph
    session_factory = request.app.state.session_factory
    memory_manager = request.app.state.memory_manager
    with session_factory() as session:
        record = session.get(InvestigationModel, investigation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    result = resume_investigation(graph, investigation_id=investigation_id)
    final_status = result.get("status", record.status)
    report = result.get("report") if isinstance(result, dict) else None
    with session_factory() as session:
        db_record = session.get(InvestigationModel, investigation_id)
        if db_record is not None:
            db_record.status = final_status
            db_record.summary = (report or {}).get("summary") if isinstance(report, dict) else db_record.summary
            db_record.report = report if isinstance(report, dict) else db_record.report
            session.commit()
    return InvestigationRead(
        id=investigation_id,
        question=record.question,
        target_system=record.target_system,
        target_environment=record.target_environment,
        status=final_status,
        summary=(report or {}).get("summary") if isinstance(report, dict) else record.summary,
        report=report,
    )

@router.post("/investigations/{investigation_id}/cancel", response_model=InvestigationRead)
def cancel(request: Request, investigation_id: str) -> InvestigationRead:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        record = session.get(InvestigationModel, investigation_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Investigation not found")
        record.status = "cancelled"
        session.commit()
    return InvestigationRead(
        id=investigation_id,
        question=record.question,
        target_system=record.target_system,
        target_environment=record.target_environment,
        status="cancelled",
        summary=record.summary,
        report=record.report,
    )

@router.get("/investigations/{investigation_id}/report")
def get_report(request: Request, investigation_id: str) -> dict[str, Any]:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        record = session.get(InvestigationModel, investigation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return {"investigation_id": investigation_id, "report": record.report}


@router.get("/investigations/{investigation_id}/evidence")
def get_evidence(request: Request, investigation_id: str) -> dict[str, Any]:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        record = session.get(InvestigationModel, investigation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    report = record.report or {}
    return {
        "investigation_id": investigation_id,
        "observed_facts": report.get("observed_facts", []),
        "document_references": report.get("document_references", []),
        "applicability_checks": report.get("applicability_checks", []),
    }


@router.get("/investigations/{investigation_id}/audit-events")
def get_audit_events(request: Request, investigation_id: str) -> dict[str, Any]:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        record = session.get(InvestigationModel, investigation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    audit_manager = request.app.state.audit_manager
    return {
        "investigation_id": investigation_id,
        "events": audit_manager.list_events(investigation_id),
    }
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        record = session.get(InvestigationModel, investigation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return {
        "investigation_id": investigation_id,
        "status": record.status,
        "summary": record.summary,
        "report": record.report,
    }
