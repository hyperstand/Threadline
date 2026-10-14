"""M6/M8 investigation routes: create, inspect, resume, cancel, history, report, evidence, audit."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict

from threadline.audit import record_event
from threadline.orchestration.graph import resume_investigation, run_investigation
from threadline.persistence.models import InvestigationModel
from threadline.redact import redact_secrets

router = APIRouter(prefix="/api/v1", tags=["investigations"])

FAILED_SUMMARY = "Investigation failed; see the audit events for details."


class InvestigationCreate(BaseModel):
    question: str
    target_system: str
    target_environment: str
    mode: Literal["live", "document_only"] = "live"


class InvestigationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    question: str
    target_system: str | None
    target_environment: str | None
    status: str
    summary: str | None = None
    report: dict[str, Any] | None = None


class InvestigationSummary(BaseModel):
    id: str
    question: str
    target_system: str | None
    target_environment: str | None
    status: str
    summary: str | None = None
    started_at: datetime


def _get_or_404(session_factory, investigation_id: str) -> InvestigationModel:
    with session_factory() as session:
        record = session.get(InvestigationModel, investigation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return record


def _store_outcome(session_factory, investigation_id: str, result: dict[str, Any]) -> InvestigationRead:
    final_status = result.get("status", "failed")
    report = result.get("report") if isinstance(result.get("report"), dict) else None
    with session_factory() as session:
        record = session.get(InvestigationModel, investigation_id)
        record.status = final_status
        if report is not None:
            record.summary = report.get("executive_summary")
            record.report = report
        elif final_status == "failed":
            record.summary = FAILED_SUMMARY
        if final_status in {"completed", "insufficient_evidence", "failed"}:
            record.completed_at = datetime.now(UTC)
        session.commit()
        return InvestigationRead(
            id=record.id,
            question=record.question,
            target_system=record.target_system,
            target_environment=record.target_environment,
            status=record.status,
            summary=record.summary,
            report=record.report,
        )


@router.post("/investigations", response_model=InvestigationRead, status_code=status.HTTP_201_CREATED)
def create_investigation(request: Request, body: InvestigationCreate) -> InvestigationRead:
    session_factory = request.app.state.session_factory
    graph = request.app.state.investigation_graph
    memory_manager = request.app.state.memory_manager
    audit_manager = request.app.state.audit_manager
    investigation_id = str(uuid.uuid4())
    with session_factory() as session:
        session.add(
            InvestigationModel(
                id=investigation_id,
                question=body.question,
                target_system=body.target_system,
                target_environment=body.target_environment,
                status="queued",
                graph_thread_id=investigation_id,
            )
        )
        session.commit()
    record_event(
        audit_manager,
        investigation_id,
        "investigation.created",
        mode=body.mode,
        target_system=body.target_system,
        target_environment=body.target_environment,
    )
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
        record_event(
            audit_manager,
            investigation_id,
            "investigation.failed",
            status="failed",
            error=redact_secrets(str(exc))[:300],
        )
        result = {"status": "failed", "report": None}
    return _store_outcome(session_factory, investigation_id, result)


@router.get("/investigations", response_model=list[InvestigationSummary])
def list_investigations(request: Request, limit: int = Query(default=20, ge=1, le=100)) -> list[InvestigationSummary]:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        rows = (
            session.query(InvestigationModel)
            .order_by(InvestigationModel.started_at.desc())
            .limit(limit)
            .all()
        )
        return [
            InvestigationSummary(
                id=row.id,
                question=row.question,
                target_system=row.target_system,
                target_environment=row.target_environment,
                status=row.status,
                summary=row.summary,
                started_at=row.started_at,
            )
            for row in rows
        ]


@router.get("/investigations/{investigation_id}", response_model=InvestigationRead)
def get_investigation(request: Request, investigation_id: str) -> InvestigationRead:
    record = _get_or_404(request.app.state.session_factory, investigation_id)
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
    audit_manager = request.app.state.audit_manager
    _get_or_404(session_factory, investigation_id)
    record_event(audit_manager, investigation_id, "investigation.resumed")
    try:
        result = resume_investigation(graph, investigation_id=investigation_id)
    except Exception as exc:
        record_event(
            audit_manager,
            investigation_id,
            "investigation.failed",
            status="failed",
            error=redact_secrets(str(exc))[:300],
        )
        result = {"status": "failed", "report": None}
    return _store_outcome(session_factory, investigation_id, result)


@router.post("/investigations/{investigation_id}/cancel", response_model=InvestigationRead)
def cancel(request: Request, investigation_id: str) -> InvestigationRead:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        record = session.get(InvestigationModel, investigation_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Investigation not found")
        record.status = "cancelled"
        session.commit()
        result = InvestigationRead(
            id=investigation_id,
            question=record.question,
            target_system=record.target_system,
            target_environment=record.target_environment,
            status="cancelled",
            summary=record.summary,
            report=record.report,
        )
    record_event(request.app.state.audit_manager, investigation_id, "investigation.cancelled")
    return result


@router.get("/investigations/{investigation_id}/report")
def get_report(request: Request, investigation_id: str) -> dict[str, Any]:
    record = _get_or_404(request.app.state.session_factory, investigation_id)
    return {"investigation_id": investigation_id, "report": record.report}


@router.get("/investigations/{investigation_id}/evidence")
def get_evidence(request: Request, investigation_id: str) -> dict[str, Any]:
    record = _get_or_404(request.app.state.session_factory, investigation_id)
    report = record.report or {}
    return {
        "investigation_id": investigation_id,
        "observed_facts": report.get("observed_facts", []),
        "document_references": report.get("document_references", []),
        "applicability_checks": report.get("applicability_checks", []),
    }


@router.get("/investigations/{investigation_id}/audit-events")
def get_audit_events(request: Request, investigation_id: str) -> dict[str, Any]:
    _get_or_404(request.app.state.session_factory, investigation_id)
    audit_manager = request.app.state.audit_manager
    return {
        "investigation_id": investigation_id,
        "events": audit_manager.list_events(investigation_id),
    }
