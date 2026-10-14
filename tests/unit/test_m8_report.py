"""M8 structured report, citation validation, and audit recording (PRD FR-07, FR-11)."""

from __future__ import annotations

import pytest

from threadline.audit import record_event
from threadline.evidence.citations import validate_report_citations
from threadline.evidence.models import InvestigationReport, ObservedFact, ReportScope
from threadline.orchestration.nodes import assess_applicability, generate_report, retrieve_documents


class RecordingAudit:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def record(self, investigation_id, event_type, *, status="completed", actor_type="system", actor_id=None, safe_metadata=None, correlation_id=None):
        self.events.append({"investigation_id": investigation_id, "event_type": event_type, "status": status, "safe_metadata": safe_metadata or {}})


class BrokenAudit:
    def record(self, *args, **kwargs):
        raise RuntimeError("database is locked")


def _state(**overrides) -> dict:
    base = {
        "investigation_id": "inv-1",
        "question": "postgres replication lag",
        "target_system": "postgres",
        "target_environment": "dev",
        "plan": ["Retrieve operational documentation."],
        "retrieved_chunks": [
            {"chunk_id": "c1", "content": "check replication lag", "document_id": "d1", "source_name": "runbook.txt", "system_scope": "postgres", "environment_scope": "dev"},
            {"chunk_id": "c2", "content": "legacy steps", "document_id": "d2", "source_name": "legacy.txt", "system_scope": "postgres", "environment_scope": "prod"},
        ],
        "retrieved_document_ids": ["c1", "c2"],
        "live_evidence": [
            {
                "evidence_id": "obs-sim",
                "adapter": "fake",
                "tool_name": "get_service_status",
                "target_system": "postgres",
                "target_environment": "dev",
                "observed_at": "2026-10-14T00:00:00+00:00",
                "result": {"service": "postgres", "environment": "dev", "status": "available"},
            }
        ],
        "limitations": [],
        "missing_information": [],
        "status": "running",
    }
    base.update(overrides)
    # The graph always runs assess_applicability before generate_report.
    if "applicability_checks" not in overrides:
        base["applicability_checks"] = assess_applicability(base)["applicability_checks"]
    return base


def test_report_has_fr07_sections_and_typed_schema() -> None:
    update = generate_report(_state())
    report = InvestigationReport.model_validate(update["report"])
    assert report.run_id == "inv-1"
    assert report.target_scope == ReportScope(system="postgres", environment="dev")
    assert report.executive_summary
    assert report.hypotheses == []
    assert report.disclaimer
    assert report.investigation_plan == ["Retrieve operational documentation."]
    assert update["status"] == "completed"


def test_document_references_carry_applicability_status() -> None:
    report = InvestigationReport.model_validate(generate_report(_state())["report"])
    statuses = {ref.source_name: ref.applicability_status for ref in report.document_references}
    assert statuses == {"runbook.txt": "confirmed", "legacy.txt": "contradicted"}


def test_simulated_observation_is_labelled_unverified_and_summary_says_so() -> None:
    report = InvestigationReport.model_validate(generate_report(_state())["report"])
    fact = report.observed_facts[0]
    assert fact.simulated is True
    assert fact.trust_status == "unverified"
    assert "simulated" in report.executive_summary


def test_no_evidence_yields_insufficient_evidence_without_error() -> None:
    state = _state(retrieved_chunks=[], retrieved_document_ids=[], live_evidence=[])
    update = generate_report(state)
    assert update["status"] == "insufficient_evidence"
    report = InvestigationReport.model_validate(update["report"])
    assert "no conclusion can be drawn" in report.executive_summary.lower()
    assert any("Index runbooks" in step for step in report.recommended_next_steps)


def test_uncertainty_lists_every_non_confirmed_check() -> None:
    report = InvestigationReport.model_validate(generate_report(_state())["report"])
    assert any(item.startswith("contradicted:") for item in report.uncertainty)
    assert all(not item.startswith("confirmed:") for item in report.uncertainty)


def test_citation_to_unretrieved_evidence_is_rejected() -> None:
    report = InvestigationReport(
        run_id="inv-2",
        request="q",
        target_scope=ReportScope(system="postgres", environment="dev"),
        executive_summary="s",
        observed_facts=[ObservedFact(evidence_id="obs-fabricated", source="x", excerpt="", trust_status="observed")],
    )
    with pytest.raises(ValueError, match="obs-fabricated"):
        validate_report_citations(report, known_ids=["c1"])


def test_citation_to_retrieved_evidence_passes() -> None:
    report = InvestigationReport(
        run_id="inv-3",
        request="q",
        target_scope=ReportScope(system="postgres", environment="dev"),
        executive_summary="s",
        observed_facts=[ObservedFact(evidence_id="obs-1", source="x", excerpt="", trust_status="observed")],
    )
    validate_report_citations(report, known_ids=["obs-1"])


def test_retrieval_failure_is_recorded_not_silently_empty() -> None:
    audit = RecordingAudit()

    def failing_retrieval(query, filters, limit):
        raise RuntimeError("fts index missing")

    update = retrieve_documents(_state(), failing_retrieval, "postgres", audit_manager=audit)
    assert update["retrieved_chunks"] == []
    assert any("retrieval failed" in item.lower() for item in update["limitations"])
    assert [event["event_type"] for event in audit.events] == ["retrieval.failed"]
    assert audit.events[0]["status"] == "failed"


def test_retrieval_maps_object_results_and_keeps_scope_metadata() -> None:
    class Hit:
        def model_dump(self):
            return {
                "id": "chunk-9",
                "content": "replication lag steps",
                "source_id": "runbook.txt",
                "version": "h1",
                "metadata": {"document_id": "doc-9", "system_scope": "postgres", "environment_scope": "dev", "page_number": 2},
            }

    update = retrieve_documents(_state(), lambda q, f, l: [Hit(), Hit()], "postgres")
    assert update["retrieved_document_ids"] == ["chunk-9"]
    chunk = update["retrieved_chunks"][0]
    assert chunk["document_id"] == "doc-9"
    assert chunk["environment_scope"] == "dev"
    assert chunk["page_number"] == 2


def test_audit_write_failure_is_logged_and_does_not_break_workflow() -> None:
    record_event(BrokenAudit(), "inv-4", "tool.invoked", tool_name="x")


def test_audit_is_skipped_when_no_manager_configured() -> None:
    record_event(None, "inv-5", "tool.invoked", tool_name="x")
